# Portaria UNIARTE — Controle de Acesso (web)

Migração do sistema Access "Controle de Acesso Bison" para Python (FastAPI) + SQLAlchemy + Bootstrap 5.
Banco: SQLite localmente, PostgreSQL no servidor (só muda `DATABASE_URL`).

## Rodar localmente
Requer Python 3.11+ (https://www.python.org/downloads/ — marque "Add to PATH").

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # edite ADMIN_PASSWORD e SECRET_KEY
python -m migracao.importar   # importa migracao\dados (já exportado do Access)
uvicorn app.main:app --reload
```
Acesse http://localhost:8000 (usuário/senha do `.env`; troque depois em *Usuários*).
Para acessar de outro computador da rede: `uvicorn app.main:app --host 0.0.0.0`.

Para reexportar do Access: `powershell -ExecutionPolicy Bypass -File migracao\exportar_access.ps1 -Origem "<arquivo.accdb>" -Destino migracao\dados`

## Subir para um servidor
1. VPS Linux com Docker. Copie o projeto e crie `.env` com `SECRET_KEY`, `ADMIN_PASSWORD`, `DB_PASSWORD`.
2. `docker compose up -d`; importe os dados: `docker compose run --rm -v ./migracao/dados:/srv/migracao/dados web python -m migracao.importar`
3. Coloque Caddy/Nginx com HTTPS (Let's Encrypt) apontando para a porta 8000 e mantenha `COOKIE_SECURE=true`.

## Mapeamento Access → novo modelo
| Access | Novo |
|---|---|
| tblMoradores | `unidades` + `pessoas` (moradores/autorizados/diarista) + `veiculos` |
| tblVisitantes / tblEntregas | `registros` (tipo VISITANTE, PRESTADOR, ENTREGA; agora com hora de saída) |
| tbl_CadUsuarios | `usuarios` (senhas com hash; a senha antiga não é importada) |

Premissas a conferir: autorizados 1–3 ↔ CPF/Telefone 5–7 e diarista ↔ CPF/Telefone 8; as colunas "SIM/NÃO" do Access não foram mapeadas (ficam preservadas em `unidades.legado`).
