"""Inicializador Desktop (Windows) da Portaria UNIARTE com Auto-Atualização Remota via GitHub.

1. Verifica no repositório GitHub (matheushns/PORTARIA-UNIARTE) se há um commit novo.
2. Caso exista, baixa o zip da branch master e atualiza a pasta local `app/` (código Python,
   templates HTML e arquivos estáticos CSS/JS/ícones) antes de importar o FastAPI.
3. Inicia o servidor FastAPI em uma porta local livre em segundo plano e abre a janela nativa.
"""
import importlib.util
import io
import json
import os
import shutil
import socket
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

# Quando empacotado pelo PyInstaller (--noconsole), garante diretório de trabalho na pasta do .exe
if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))

PASTA_BASE = Path.cwd()
PASTA_APP_REMOTO = PASTA_BASE / "app_atualizado"
ARQUIVO_VERSAO = PASTA_BASE / ".versao_commit"
GITHUB_REPO = "matheushns/PORTARIA-UNIARTE"
GITHUB_BRANCH = "master"


def verificar_e_atualizar():
    """Consulta o último commit no GitHub e atualiza a pasta `app_atualizado/app` se houver novidade."""
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{GITHUB_REPO}/commits/{GITHUB_BRANCH}",
            headers={"User-Agent": "PortariaUNIARTE-Updater/1.0", "Accept": "application/vnd.github.v3+json"},
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
            sha_remoto = dados.get("sha", "")
        if not sha_remoto:
            return

        sha_local = ARQUIVO_VERSAO.read_text(encoding="utf-8").strip() if ARQUIVO_VERSAO.exists() else ""
        if sha_remoto == sha_local and (PASTA_APP_REMOTO / "app" / "main.py").exists():
            return

        # Baixa o zip da branch master
        url_zip = f"https://github.com/{GITHUB_REPO}/archive/refs/heads/{GITHUB_BRANCH}.zip"
        req_zip = urllib.request.Request(url_zip, headers={"User-Agent": "PortariaUNIARTE-Updater/1.0"})
        with urllib.request.urlopen(req_zip, timeout=12) as resp_zip:
            zip_bytes = resp_zip.read()

        pasta_tmp = PASTA_BASE / "app_atualizado_tmp"
        if pasta_tmp.exists():
            shutil.rmtree(pasta_tmp, ignore_errors=True)
        pasta_tmp.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            prefixo = f"{GITHUB_REPO.split('/')[1]}-{GITHUB_BRANCH}/app/"
            for m in zf.infolist():
                if m.filename.startswith(prefixo) and not m.is_dir():
                    rel = m.filename[len(prefixo) :]
                    destino = pasta_tmp / "app" / rel
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    destino.write_bytes(zf.read(m))

        if (pasta_tmp / "app" / "main.py").exists():
            if PASTA_APP_REMOTO.exists():
                shutil.rmtree(PASTA_APP_REMOTO, ignore_errors=True)
            pasta_tmp.rename(PASTA_APP_REMOTO)
            ARQUIVO_VERSAO.write_text(sha_remoto, encoding="utf-8")
    except Exception:
        # Se estiver sem internet ou GitHub indisponível, segue normalmente com a versão local
        pass


def carregar_app():
    """Se houver atualização baixada em `app_atualizado/app`, prioriza ela no sys.path."""
    if getattr(sys, "frozen", False):
        verificar_e_atualizar()
        if (PASTA_APP_REMOTO / "app" / "main.py").exists():
            sys.path.insert(0, str(PASTA_APP_REMOTO))
            # Remove eventual cache do pacote app congelado para carregar os arquivos novos do disco
            for mod in list(sys.modules.keys()):
                if mod == "app" or mod.startswith("app."):
                    del sys.modules[mod]
            spec = importlib.util.spec_from_file_location(
                "app",
                str(PASTA_APP_REMOTO / "app" / "__init__.py"),
                submodule_search_locations=[str(PASTA_APP_REMOTO / "app")],
            )
            if spec and spec.loader:
                pkg = importlib.util.module_from_spec(spec)
                sys.modules["app"] = pkg
                spec.loader.exec_module(pkg)

    from app.main import app as fastapi_app

    return fastapi_app


def _porta_livre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _aguardar_servidor(url: str, timeout: float = 15.0):
    inicio = time.time()
    while time.time() - inicio < timeout:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return
        except Exception:
            time.sleep(0.1)


def main():
    import uvicorn
    import webview

    # Garante que todas as bibliotecas usadas pelo app estejam incluídas pelo PyInstaller
    import fastapi  # noqa: F401
    import jinja2  # noqa: F401
    import psycopg  # noqa: F401
    import sqlalchemy  # noqa: F401
    import starlette.middleware.sessions  # noqa: F401

    fastapi_app = carregar_app()

    porta = _porta_livre()
    url = f"http://127.0.0.1:{porta}/login"

    config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=porta, log_level="warning")
    servidor = uvicorn.Server(config)

    t = threading.Thread(target=servidor.run, daemon=True)
    t.start()

    _aguardar_servidor(url)

    webview.create_window(
        title="Portaria UNIARTE",
        url=url,
        width=1360,
        height=840,
        min_size=(960, 620),
        text_select=True,
    )
    webview.start()
    servidor.should_exit = True


if __name__ == "__main__":
    main()
