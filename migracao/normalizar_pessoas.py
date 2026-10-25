"""Move 'parentesco' e 'liberação' que estavam digitados dentro do nome (ex.: 'ANA (MÃE, LIBERADA)')
para os campos próprios. Pode ser executado mais de uma vez com segurança.

Uso:  python -m migracao.normalizar_pessoas
"""
from app.database import SessionLocal, garantir_colunas
from app.models import Pessoa
from migracao.importar import extrair_obs


def main():
    garantir_colunas()
    with SessionLocal() as db:
        n_par = n_lib = n_nome = 0
        for p in db.query(Pessoa).all():
            nome, par, lib = extrair_obs(p.nome)
            if not nome:  # nunca deixar o nome vazio
                continue
            if par and not p.parentesco:
                p.parentesco, n_par = par, n_par + 1
            if lib and not p.liberacao:
                p.liberacao, n_lib = lib, n_lib + 1
            if nome != p.nome and (par or lib):
                p.nome, n_nome = nome, n_nome + 1
        db.commit()
    print(f"Parentescos: {n_par} | Liberações: {n_lib} | Nomes limpos: {n_nome}")


if __name__ == "__main__":
    main()
