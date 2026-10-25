"""Inicializador Desktop (Windows) da Portaria UNIARTE com Auto-Atualização Remota via GitHub.

1. Abre imediatamente a janela principal com uma tela de carregamento ("Abrindo o programa, aguarde...").
2. Verifica no repositório GitHub (matheushns/PORTARIA-UNIARTE) se há um commit novo.
3. Caso exista, baixa o zip da branch master e atualiza a pasta local `app/` antes de importar o FastAPI.
4. Inicia o servidor FastAPI em uma porta local livre em segundo plano e carrega o sistema na janela.
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


def carregar_app(callback_status=None):
    """Se houver atualização baixada em `app_atualizado/app`, prioriza ela no sys.path."""
    if getattr(sys, "frozen", False):
        if callback_status:
            callback_status("Verificando atualizações do sistema...")
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

    if callback_status:
        callback_status("Carregando módulos e banco de dados...")
    from app.main import app as fastapi_app

    return fastapi_app


def _porta_livre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _aguardar_servidor(url: str, timeout: float = 20.0):
    inicio = time.time()
    while time.time() - inicio < timeout:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return
        except Exception:
            time.sleep(0.1)


SPLASH_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; user-select: none; }
  body {
    height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: radial-gradient(circle at center, #1e3a5f 0%, #0f1e33 100%);
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    color: #ffffff;
    overflow: hidden;
  }
  .card {
    text-align: center;
    padding: 44px 52px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 20px;
    box-shadow: 0 25px 60px rgba(0, 0, 0, 0.45);
    max-width: 460px;
    width: 90%;
  }
  .icon-wrap {
    width: 84px;
    height: 84px;
    margin: 0 auto 20px;
    border-radius: 20px;
    background: linear-gradient(135deg, #2d5a8e, #163052);
    border: 2px solid #f0b429;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.35);
  }
  .icon-wrap svg {
    width: 46px;
    height: 46px;
  }
  h1 {
    font-size: 24px;
    font-weight: 700;
    letter-spacing: 0.4px;
    margin-bottom: 6px;
  }
  .subtitle {
    font-size: 13.5px;
    color: #a8c0dd;
    margin-bottom: 28px;
  }
  .spinner {
    width: 42px;
    height: 42px;
    margin: 0 auto 18px;
    border: 4px solid rgba(255, 255, 255, 0.15);
    border-top-color: #f0b429;
    border-radius: 50%;
    animation: spin 0.85s linear infinite;
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  .status {
    font-size: 14px;
    font-weight: 600;
    color: #f0b429;
    min-height: 22px;
  }
  .hint {
    font-size: 12px;
    color: #8da9c8;
    margin-top: 10px;
  }
</style>
</head>
<body>
  <div class="card">
    <div class="icon-wrap">
      <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M32 6L10 15V31C10 45.2 19.4 57.6 32 61C44.6 57.6 54 45.2 54 31V15L32 6Z" fill="#1E3A5F" stroke="#F0B429" stroke-width="3"/>
        <rect x="21" y="22" width="22" height="26" rx="2" fill="#FFFFFF"/>
        <rect x="25" y="26" width="5" height="5" rx="1" fill="#1E3A5F"/>
        <rect x="34" y="26" width="5" height="5" rx="1" fill="#1E3A5F"/>
        <rect x="25" y="34" width="5" height="5" rx="1" fill="#1E3A5F"/>
        <rect x="34" y="34" width="5" height="5" rx="1" fill="#1E3A5F"/>
        <rect x="29" y="41" width="6" height="7" fill="#F0B429"/>
      </svg>
    </div>
    <h1>Portaria UNIARTE</h1>
    <div class="subtitle">Sistema de Controle de Acesso</div>
    <div class="spinner"></div>
    <div id="status-msg" class="status">Abrindo o programa, aguarde...</div>
    <div class="hint">Iniciando serviços e conexão com banco de dados em nuvem</div>
  </div>
  <script>
    function atualizarStatus(msg) {
      var el = document.getElementById('status-msg');
      if (el) el.textContent = msg;
    }
  </script>
</body>
</html>
"""


# Dica estática para o PyInstaller empacotar todas as dependências do backend
if False:  # pragma: no cover
    import fastapi  # noqa: F401
    import jinja2  # noqa: F401
    import psycopg  # noqa: F401
    import sqlalchemy  # noqa: F401
    import starlette.middleware.sessions  # noqa: F401
    import uvicorn  # noqa: F401


def main():
    import webview

    pasta_cookies = PASTA_BASE / ".webview_cache"
    pasta_cookies.mkdir(parents=True, exist_ok=True)

    servidor_ref = {"instancia": None}

    janela = webview.create_window(
        title="Portaria UNIARTE",
        html=SPLASH_HTML,
        width=1360,
        height=840,
        min_size=(960, 620),
        text_select=True,
        background_color="#0f1e33",
    )

    def _set_status(texto: str):
        try:
            janela.evaluate_js(f"atualizarStatus({json.dumps(texto)});")
        except Exception:
            pass

    def _inicializar_sistema():
        import uvicorn

        fastapi_app = carregar_app(callback_status=_set_status)

        porta = _porta_livre()
        url = f"http://127.0.0.1:{porta}/"

        _set_status("Conectando ao servidor e banco de dados...")
        config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=porta, log_level="warning")
        servidor = uvicorn.Server(config)
        servidor_ref["instancia"] = servidor

        t = threading.Thread(target=servidor.run, daemon=True)
        t.start()

        _aguardar_servidor(f"http://127.0.0.1:{porta}/login")
        _set_status("Abrindo painel da portaria...")
        janela.load_url(url)

    webview.start(_inicializar_sistema, private_mode=False, storage_path=str(pasta_cookies))

    # Atualiza o carimbo de hora ao fechar a janela para contar 1 hora exata a partir do fechamento
    arq_sessao = PASTA_BASE / ".sessao_ativa.json"
    if arq_sessao.exists():
        try:
            d = json.loads(arq_sessao.read_text(encoding="utf-8"))
            if d.get("uid"):
                d["ts"] = time.time()
                arq_sessao.write_text(json.dumps(d), encoding="utf-8")
        except Exception:
            pass
    if servidor_ref["instancia"] is not None:
        servidor_ref["instancia"].should_exit = True


if __name__ == "__main__":
    main()
