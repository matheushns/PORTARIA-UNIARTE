"""Gerenciador de Atualizações Remotas (Portaria UNIARTE).

Suporta duas modalidades de atualização via GitHub (matheushns/PORTARIA-UNIARTE):
1. Atualização Rápida (Código/Telas): verifica o último commit da branch `master` e baixa
   a pasta `app/` atualizada sem precisar reinstalar o executável.
2. Atualização do Instalador Completo (.exe): verifica a última Release publicada no GitHub
   (`releases/latest`) e, se a tag for superior à VERSAO_INSTALADOR local, permite baixar
   e iniciar o `Instalador_PortariaUNIARTE_Setup.exe` automaticamente.
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

VERSAO_INSTALADOR = "1.0.0"
GITHUB_REPO = "matheushns/PORTARIA-UNIARTE"
GITHUB_BRANCH = "master"
HEADERS = {
    "User-Agent": "PortariaUNIARTE-Updater/1.0",
    "Accept": "application/vnd.github.v3+json",
}


def pasta_base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()


def pasta_app_remoto() -> Path:
    return pasta_base() / "app_atualizado"


def arquivo_versao_commit() -> Path:
    return pasta_base() / ".versao_commit"


def arquivo_versao_instalador() -> Path:
    return pasta_base() / ".versao_instalador_ok"


def _tupla_versao(v: str) -> tuple[int, ...]:
    nums = [int(x) for x in re.findall(r"\d+", v or "")]
    return tuple(nums) if nums else (0,)


def obter_versao_instalador_local() -> str:
    arq = arquivo_versao_instalador()
    if arq.exists():
        txt = arq.read_text(encoding="utf-8").strip()
        if txt:
            return txt
    return VERSAO_INSTALADOR


def obter_commit_local() -> str:
    arq = arquivo_versao_commit()
    if arq.exists():
        return arq.read_text(encoding="utf-8").strip()
    return ""


def _get_json(url: str, timeout: float = 5.0) -> dict | None:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def consultar_status_remoto(timeout: float = 5.0) -> dict:
    """Retorna informações sobre atualizações disponíveis (código e instalador completo)."""
    commit_local = obter_commit_local()
    versao_inst_local = obter_versao_instalador_local()

    out = {
        "ok": True,
        "commit_local": commit_local[:7] if commit_local else "original",
        "commit_remoto": "",
        "commit_mensagem": "",
        "commit_data": "",
        "tem_atualizacao_codigo": False,
        "versao_instalador_local": versao_inst_local,
        "versao_instalador_remota": versao_inst_local,
        "instalador_url": "",
        "instalador_notas": "",
        "tem_atualizacao_instalador": False,
    }

    # 1. Consulta último commit da branch master
    try:
        dados_c = _get_json(f"https://api.github.com/repos/{GITHUB_REPO}/commits/{GITHUB_BRANCH}", timeout=timeout)
        if dados_c and dados_c.get("sha"):
            sha = dados_c["sha"]
            out["commit_remoto"] = sha[:7]
            out["commit_sha_completo"] = sha
            commit_info = dados_c.get("commit") or {}
            out["commit_mensagem"] = (commit_info.get("message") or "").splitlines()[0]
            if not commit_local:
                # Primeira execução: registra o commit atual como base caso já esteja sincronizado
                arquivo_versao_commit().write_text(sha, encoding="utf-8")
                out["commit_local"] = sha[:7]
            elif sha != commit_local:
                out["tem_atualizacao_codigo"] = True
    except Exception as exc:
        out["ok"] = False
        out["erro"] = f"Não foi possível consultar o GitHub: {exc}"

    # 2. Consulta última Release para instalador completo (.exe)
    try:
        dados_r = _get_json(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest", timeout=timeout)
        if dados_r and dados_r.get("tag_name"):
            tag = dados_r["tag_name"].lstrip("vV").strip()
            out["versao_instalador_remota"] = tag
            out["instalador_notas"] = dados_r.get("body") or dados_r.get("name") or ""
            for asset in dados_r.get("assets") or []:
                nome = (asset.get("name") or "").lower()
                if nome.endswith(".exe"):
                    out["instalador_url"] = asset.get("browser_download_url") or ""
                    break
            if _tupla_versao(tag) > _tupla_versao(versao_inst_local) and out["instalador_url"]:
                out["tem_atualizacao_instalador"] = True
    except urllib.error.HTTPError as e:
        # 404 significa que ainda não há nenhuma Release publicada no repositório (normal)
        if e.code != 404:
            pass
    except Exception:
        pass

    return out


def aplicar_atualizacao_codigo(sha_esperado: str = "") -> dict:
    """Baixa o zip da branch master e atualiza `app/` local."""
    try:
        if not sha_esperado:
            st = consultar_status_remoto(timeout=6.0)
            sha_esperado = st.get("commit_sha_completo", "")

        url_zip = f"https://github.com/{GITHUB_REPO}/archive/refs/heads/{GITHUB_BRANCH}.zip"
        req_zip = urllib.request.Request(url_zip, headers=HEADERS)
        with urllib.request.urlopen(req_zip, timeout=15) as resp_zip:
            zip_bytes = resp_zip.read()

        base = pasta_base()
        alvos = [base / "app_atualizado" / "app"]
        # Se estiver rodando direto na pasta de código ou _internal existir, atualiza também templates/static
        internal_app = base / "_internal" / "app"
        if internal_app.exists():
            alvos.append(internal_app)
        elif (base / "app" / "main.py").exists() and not getattr(sys, "frozen", False):
            alvos.append(base / "app")

        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            prefixo = f"{GITHUB_REPO.split('/')[1]}-{GITHUB_BRANCH}/app/"
            arquivos = [m for m in zf.infolist() if m.filename.startswith(prefixo) and not m.is_dir()]
            if not arquivos:
                return {"ok": False, "mensagem": "Pacote baixado não contém a pasta app/."}

            for alvo in alvos:
                for m in arquivos:
                    rel = m.filename[len(prefixo) :]
                    destino = alvo / rel
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    destino.write_bytes(zf.read(m))

        if sha_esperado:
            arquivo_versao_commit().write_text(sha_esperado, encoding="utf-8")

        return {
            "ok": True,
            "mensagem": "Atualização rápida aplicada com sucesso! A página será recarregada.",
        }
    except Exception as exc:
        return {"ok": False, "mensagem": f"Erro ao baixar atualização: {exc}"}


def baixar_e_executar_instalador(url_exe: str, nova_versao: str = "") -> dict:
    """Baixa o Instalador_PortariaUNIARTE_Setup.exe da Release, inicia de forma independente e fecha o app atual."""
    if not url_exe:
        return {"ok": False, "mensagem": "Nenhum instalador (.exe) encontrado na Release do GitHub."}
    try:
        req = urllib.request.Request(url_exe, headers=HEADERS)
        pasta_tmp = Path(tempfile.gettempdir())
        destino = pasta_tmp / "Instalador_PortariaUNIARTE_Setup.exe"
        with urllib.request.urlopen(req, timeout=90) as resp:
            destino.write_bytes(resp.read())

        cmd = [str(destino), "--pasta", str(pasta_base())]
        if nova_versao:
            cmd.extend(["--versao", str(nova_versao).lstrip("vV").strip()])

        # Inicia o instalador totalmente desvinculado (sem herdar descritores/arquivos abertos)
        flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
        )
        subprocess.Popen(
            cmd,
            cwd=str(pasta_tmp),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=flags,
        )

        # Fecha o programa atual 1.2s depois para liberar todos os arquivos (.exe / .dll) para o instalador
        if getattr(sys, "frozen", False):
            threading.Timer(1.2, lambda: os._exit(0)).start()

        return {
            "ok": True,
            "mensagem": "Instalador baixado e iniciado! O programa será fechado para concluir a atualização.",
        }
    except Exception as exc:
        return {"ok": False, "mensagem": f"Erro ao baixar o instalador completo: {exc}"}
