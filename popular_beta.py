"""Popula o banco BETA (SQLite local) com moradores FICTÍCIOS para testes.

Uso (pelo popular_beta.bat): só roda em modo BETA com SQLite; nunca toca o Supabase.
Cada execução ADICIONA mais unidades fictícias (as existentes nunca são alteradas).
"""
import os
import random
import sys

if not os.getenv("PORTARIA_BETA"):
    sys.exit("Recusado: defina PORTARIA_BETA=1 (use popular_beta.bat). Este script é só para o banco BETA.")

from app import config  # noqa: E402  (levanta erro se não for SQLite)
from app.database import Base, SessionLocal, engine, garantir_colunas  # noqa: E402
from app.models import PARENTESCOS, Pessoa, Unidade, Veiculo  # noqa: E402

if not config.DATABASE_URL.startswith("sqlite"):
    sys.exit("Recusado: banco não é SQLite.")

random.seed(2026)
NOMES = ["Ana", "Bruno", "Carla", "Diego", "Elaine", "Fábio", "Gabriela", "Hugo", "Isabela", "João", "Karina",
         "Lucas", "Mariana", "Nelson", "Olívia", "Paulo", "Queila", "Rafael", "Sandra", "Tiago", "Úrsula",
         "Vinícius", "Wanda", "Xavier", "Yara", "Zeca", "Beatriz", "Caio", "Débora", "Eduardo"]
SOBRENOMES = ["Silva", "Souza", "Oliveira", "Santos", "Lima", "Pereira", "Costa", "Ferreira", "Almeida", "Ribeiro",
              "Carvalho", "Gomes", "Martins", "Rocha", "Barbosa", "Araújo", "Moreira", "Nunes", "Teixeira", "Dias"]
VEICULOS = [("Gol", "Prata"), ("Onix", "Branco"), ("HB20", "Preto"), ("Civic", "Cinza"), ("Corolla", "Branco"),
            ("Palio", "Vermelho"), ("Fiesta", "Azul"), ("Uno", "Branco"), ("Kwid", "Laranja"), ("Argo", "Cinza")]
APTOS = [f"{andar}0{num}" for andar in range(1, 5) for num in range(1, 5)]
_seq = {"tel": 0, "cpf": 0}


def nome():
    return f"{random.choice(NOMES)} {random.choice(SOBRENOMES)} {random.choice(SOBRENOMES)}".upper()


def tel():
    _seq["tel"] += 1
    return f"(11) 90000-{_seq['tel']:04d}"  # faixa fictícia


def cpf():
    _seq["cpf"] += 1
    n = f"{_seq['cpf']:06d}"
    return f"000.{n[:3]}.{n[3:]}-00"  # claramente fictício


def placa():
    return f"{''.join(random.choices('ABCDEFGHJKLMNPRSTUVWXYZ', k=3))}{random.randint(1, 9)}{random.choice('ABCDEFGH')}{random.randint(10, 99)}"


Base.metadata.create_all(engine)
garantir_colunas()
db = SessionLocal()
existentes = {b for (b,) in db.query(Unidade.bloco_apto).all()}
criadas = 0
for bloco in range(1, 16):
    for apto in random.sample(APTOS, k=random.randint(4, 8)):
        chave = f"{bloco:02d}/{apto}"
        if chave in existentes:
            continue
        prop = nome()
        u = Unidade(bloco_apto=chave, ativo=random.random() > 0.05, proprietario=prop, cpf=cpf(), telefone=tel(),
                    email=f"{prop.split()[0].lower()}{bloco}{apto}@exemplo.com", observacoes="[FICTÍCIO] dado de teste",
                    interfonar_1=prop.split()[0].title())
        if random.random() < 0.35:   # alugado
            inq = nome()
            u.inquilino, u.inquilino_nome, u.inquilino_cpf, u.inquilino_telefone = True, inq, cpf(), tel()
            u.inquilino_email = f"{inq.split()[0].lower()}@exemplo.com"
        responsavel = u.inquilino_nome if u.inquilino else prop
        sobrenome = responsavel.split()[-1]
        for i in range(random.randint(0, 3)):
            u.pessoas.append(Pessoa(tipo="MORADOR", nome=f"{random.choice(NOMES)} {sobrenome}".upper(), cpf=cpf(),
                                    telefone=tel() if random.random() < 0.7 else "",
                                    parentesco=random.choice(PARENTESCOS), liberacao="LIBERADO"))
        for i in range(random.randint(0, 2)):
            u.pessoas.append(Pessoa(tipo="AUTORIZADO", nome=nome(), cpf=cpf(), telefone=tel(),
                                    parentesco=random.choice(["AMIGO(A)", "TIO(A)", "PRIMO(A)"]),
                                    liberacao=random.choice(["LIBERADO", "LIBERADO", "NÃO LIBERADO"])))
        if random.random() < 0.25:
            u.pessoas.append(Pessoa(tipo="DIARISTA", nome=nome(), cpf=cpf(), telefone=tel(), liberacao="LIBERADO"))
        for i in range(random.randint(0, 2)):
            modelo, cor = random.choice(VEICULOS)
            u.veiculos.append(Veiculo(modelo=modelo, cor=cor, placa=placa()))
        db.add(u)
        criadas += 1
db.commit()
print(f"Banco beta: {criadas} unidades fictícias criadas ({db.query(Unidade).count()} no total).")
db.close()
