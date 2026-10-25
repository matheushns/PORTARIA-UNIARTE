"""Copia todos os dados do banco local SQLite (data/portaria.db) para um banco PostgreSQL remoto.

Uso:
    python -m migracao.sqlite_para_postgres "postgresql://usuario:senha@host/banco" [--limpar]
    (ou defina PG_DATABASE_URL / DATABASE_URL no ambiente)
"""
import os
import re
import sys

from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Pessoa, Registro, Unidade, Usuario, Veiculo


def normalizar_url_pg(url: str) -> str:
    url = url.strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    if "sslmode=" not in url and "localhost" not in url and "127.0.0.1" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


def truncar_campos(obj, model):
    """Garante que nenhum texto legado do SQLite ultrapasse o VARCHAR(N) do PostgreSQL."""
    for col in model.__table__.columns:
        val = getattr(obj, col.name, None)
        if isinstance(val, str):
            val = re.sub(r"\s{2,}", " ", val).strip()
            maxlen = getattr(col.type, "length", None)
            if maxlen and len(val) > maxlen:
                val = val[:maxlen].strip()
            setattr(obj, col.name, val)


def main():
    args = [a for a in sys.argv[1:] if a != "--limpar"]
    limpar = "--limpar" in sys.argv

    pg_url = args[0] if args else os.getenv("PG_DATABASE_URL") or os.getenv("DATABASE_URL", "")
    if not pg_url or pg_url.startswith("sqlite"):
        sys.exit(
            "Informe a URL do PostgreSQL.\n"
            "Exemplo:\n"
            '  python -m migracao.sqlite_para_postgres "postgresql://user:pass@host/db" --limpar'
        )

    sqlite_url = "sqlite:///./data/portaria.db"
    pg_url = normalizar_url_pg(pg_url)

    print("Conectando ao SQLite local (data/portaria.db)...")
    eng_src = create_engine(sqlite_url)
    SrcSession = sessionmaker(bind=eng_src)

    print("Conectando ao PostgreSQL remoto...")
    eng_dst = create_engine(pg_url, pool_pre_ping=True)
    DstSession = sessionmaker(bind=eng_dst, autoflush=False, expire_on_commit=False)

    print("Criando tabelas no PostgreSQL (se não existirem)...")
    Base.metadata.create_all(eng_dst)

    modelos = [
        ("usuarios", Usuario),
        ("unidades", Unidade),
        ("pessoas", Pessoa),
        ("veiculos", Veiculo),
        ("registros", Registro),
    ]

    with SrcSession() as src, DstSession() as dst:
        ja_tem = dst.query(Unidade).count()
        if ja_tem and not limpar:
            sys.exit(
                f"O PostgreSQL já possui {ja_tem} unidades cadastradas. "
                "Use a opção --limpar para substituir os dados."
            )

        if limpar:
            print("Limpando dados anteriores no PostgreSQL...")
            for _, m in reversed(modelos):
                dst.execute(delete(m))
            dst.commit()

        for nome_tb, model in modelos:
            linhas = src.scalars(select(model).order_by(model.id)).all()
            cols = [c.name for c in model.__table__.columns]
            for item in linhas:
                novo = model(**{c: getattr(item, c) for c in cols})
                truncar_campos(novo, model)
                dst.add(novo)
            dst.commit()
            print(f"  -> {nome_tb}: {len(linhas)} registros migrados.")

    # Ajusta as sequences (SERIAL/IDENTITY) do PostgreSQL para o próximo ID disponível
    with eng_dst.begin() as conn:
        for nome_tb, _ in modelos:
            conn.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{nome_tb}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {nome_tb}), 1), "
                    f"(SELECT COUNT(*) > 0 FROM {nome_tb}))"
                )
            )
    print("Sequences de IDs sincronizadas com sucesso!")
    print("Migração concluída!")


if __name__ == "__main__":
    main()
