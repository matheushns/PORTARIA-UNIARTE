import os

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL

if DATABASE_URL.startswith("sqlite"):
    os.makedirs("data", exist_ok=True)
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def garantir_colunas():
    """Adiciona colunas novas em bancos já existentes (create_all não altera tabelas)."""
    existentes_p = {c["name"] for c in inspect(engine).get_columns("pessoas")}
    existentes_u = {c["name"] for c in inspect(engine).get_columns("unidades")}
    cols_u = [
        ("inquilino_nome", "VARCHAR(200)"),
        ("inquilino_cpf", "VARCHAR(20)"),
        ("inquilino_rg", "VARCHAR(30)"),
        ("inquilino_telefone", "VARCHAR(40)"),
        ("inquilino_tel_residencial", "VARCHAR(40)"),
        ("inquilino_email", "VARCHAR(200)"),
        ("inquilino_observacoes", "TEXT"),
    ]
    with engine.begin() as conn:
        for nome in ("parentesco", "liberacao"):
            if nome not in existentes_p:
                conn.execute(text(f"ALTER TABLE pessoas ADD COLUMN {nome} VARCHAR(20) NOT NULL DEFAULT ''"))
        for nome, tipo in cols_u:
            if nome not in existentes_u:
                conn.execute(text(f"ALTER TABLE unidades ADD COLUMN {nome} {tipo} NOT NULL DEFAULT ''"))
