"""Gerenciador de Atualizações Remotas (Portaria UNIARTE).

Suporta duas modalidades de atualização via GitHub (matheushns/PORTARIA-UNIARTE):
1. Atualização Rápida (Código/Telas): verifica o último commit da branch `master` via feed Atom
   direto do GitHub (sem limite de 60 requisições/hora da API) e baixa a pasta `app/` atualizada.
2. Atualização do Instalador Completo (.exe): verifica a última Release publicada no GitHub
   (`releases/latest`) e, se a tag for superior à versão local, baixa e inicia o
   `Instalador_PortariaUNIARTE_Setup.exe` automaticamente.
"""
import io
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

VERSAO_INSTALADOR = "1.1.2"
GITHUB_REPO = "matheushns/PORTARIA-UNIARTE"
GITHUB_BRANCH = "master"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PortariaUNIARTE-Updater/1.1",
}

_CACHE_STATUS: dict = {"ts": 0.0, "dados": None}
_CACHE_TTL = 180.0  # 3 minutos para checagens automáticas de fundo


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


def _obter_ultimo_commit_atom(timeout: float = 5.0) -> tuple[str, str]:
    """Obtém (sha, mensagem) do último commit via feed Atom público (sem rate limit de API)."""
    url = f"https://github.com/{GITHUB_REPO}/commits/{GITHUB_BRANCH}.atom"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        xml_bytes = resp.read()
    root = ET.fromstring(xml_bytes)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entry = root.find("a:entry", ns)
    if entry is None:
        return "", ""
    id_el = entry.find("a:id", ns)
    title_el = entry.find("a:title", ns)
    sha = id_el.text.strip().rsplit("/", 1)[-1] if (id_el is not None and id_el.text) else ""
    msg = title_el.text.strip().splitlines()[0] if (title_el is not None and title_el.text) else ""
    return sha, msg


def _obter_ultima_release_web(timeout: float = 5.0) -> tuple[str, str]:
    """Obtém (tag, url_exe) da última Release via redirecionamento web (sem rate limit de API)."""
    url_latest = f"https://github.com/{GITHUB_REPO}/releases/latest"
    req = urllib.request.Request(url_latest, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        url_final = resp.geturl()

    # Se não houver nenhuma release publicada, o GitHub redireciona para /releases
    if "/releases/tag/" not in url_final:
        return "", ""

    tag_bruta = url_final.rsplit("/releases/tag/", 1)[-1].split("?")[0].split("#")[0].strip()
    if not tag_bruta:
        return "", ""

    # Busca link do .exe em expanded_assets/<tag_bruta>
    url_exe = ""
    try:
        url_assets = f"https://github.com/{GITHUB_REPO}/releases/expanded_assets/{tag_bruta}"
        req_a = urllib.request.Request(url_assets, headers=HEADERS)
        with urllib.request.urlopen(req_a, timeout=timeout) as resp_a:
            html_a = resp_a.read().decode("utf-8", errors="ignore")
        m = re.search(r'href=["\'](/[^"\']+?/releases/download/[^"\']+?\.exe)["\']', html_a, re.IGNORECASE)
        if m:
            url_exe = "https://github.com" + m.group(1)
    except Exception:
        pass

    if not url_exe:
        url_exe = f"https://github.com/{GITHUB_REPO}/releases/download/{tag_bruta}/Instalador_PortariaUNIARTE_Setup.exe"

    return tag_bruta.lstrip("vV").strip(), url_exe


def consultar_status_remoto(timeout: float = 5.0, forcar: bool = False) -> dict:
    """Retorna informações sobre atualizações disponíveis (código e instalador completo)."""
    agora = time.time()
    if not forcar and _CACHE_STATUS["dados"] is not None and (agora - _CACHE_STATUS["ts"] < _CACHE_TTL):
        return dict(_CACHE_STATUS["dados"])

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

    # 1. Consulta último commit da branch master (via Atom feed - sem bloqueio 403 de rate limit)
    try:
        sha, msg = _obter_ultimo_commit_atom(timeout=timeout)
        if sha:
            out["commit_remoto"] = sha[:7]
            out["commit_sha_completo"] = sha
            out["commit_mensagem"] = msg
            if not commit_local:
                arquivo_versao_commit().write_text(sha, encoding="utf-8")
                out["commit_local"] = sha[:7]
            elif sha != commit_local:
                out["tem_atualizacao_codigo"] = True
    except Exception as exc:
        out["ok"] = False
        out["erro"] = f"Não foi possível consultar o GitHub: {exc}"

    # 2. Consulta última Release para instalador completo (.exe) (via web redirect - sem bloqueio 403)
    try:
        tag, url_exe = _obter_ultima_release_web(timeout=timeout)
        if tag:
            out["versao_instalador_remota"] = tag
            out["instalador_url"] = url_exe
            if _tupla_versao(tag) > _tupla_versao(versao_inst_local) and url_exe:
                out["tem_atualizacao_instalador"] = True
    except Exception:
        pass

    if out["ok"]:
        _CACHE_STATUS["ts"] = agora
        _CACHE_STATUS["dados"] = dict(out)

    return out


def aplicar_atualizacao_codigo(sha_esperado: str = "") -> dict:
    """Baixa o zip da branch master e atualiza `app/` local."""
    try:
        if not sha_esperado:
            st = consultar_status_remoto(timeout=6.0, forcar=True)
            sha_esperado = st.get("commit_sha_completo", "")

        url_zip = f"https://github.com/{GITHUB_REPO}/archive/refs/heads/{GITHUB_BRANCH}.zip"
        req_zip = urllib.request.Request(url_zip, headers=HEADERS)
        with urllib.request.urlopen(req_zip, timeout=15) as resp_zip:
            zip_bytes = resp_zip.read()

        base = pasta_base()
        alvos = [base / "app_atualizado" / "app"]
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

        _CACHE_STATUS["ts"] = 0.0
        _CACHE_STATUS["dados"] = None

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
