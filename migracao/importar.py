"""Importa os dados exportados do Access (migracao/dados/*.json) para o novo banco.

Uso:  python -m migracao.importar [--limpar]
(execute antes migracao/exportar_access.ps1)
"""
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete

from app.database import Base, SessionLocal, engine, garantir_colunas
from app.models import Pessoa, Registro, Unidade, Veiculo

DADOS = Path(__file__).parent / "dados"


PARENTESCO = {"PAI": "PAI", "MAE": "MÃE", "FILHO": "FILHO", "FILHA": "FILHA", "GENRO": "GENRO", "SOGRO": "SOGRO",
              "TIO": "TIO", "TIA": "TIA", "AMIGO": "AMIGO", "AMIGA": "AMIGA", "ESPOSA": "ESPOSA", "ESPOSO": "ESPOSO"}
LIBERACAO = {"LIBERADO": "LIBERADO", "LIBERADA": "LIBERADO",
             "NAO LIBERADO": "NÃO LIBERADO", "NAO LIBERADA": "NÃO LIBERADO"}


def _sem_acento(x: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", x) if unicodedata.category(c) != "Mn")


def extrair_obs(nome: str):
    """'FERNANDO (GENRO, LIBERADO)' -> ('FERNANDO', 'GENRO', 'LIBERADO').
    Só remove do nome os termos reconhecidos; o restante do parêntese é mantido."""
    parentesco = liberacao = ""

    def tratar(m):
        nonlocal parentesco, liberacao
        sobra = []
        for tok in m.group(1).split(","):
            bruto = re.sub(r"\s+", " ", tok.strip().upper())
            sem = _sem_acento(bruto)
            if bruto in ("VÔ", "VÓ") and not parentesco:
                parentesco = bruto
            elif sem in PARENTESCO and not parentesco:
                parentesco = PARENTESCO[sem]
            elif sem in LIBERACAO and not liberacao:
                liberacao = LIBERACAO[sem]
            elif bruto:
                sobra.append(tok.strip())
        return "(" + ", ".join(sobra) + ")" if sobra else ""

    limpo = re.sub(r"\(([^()]*)\)", tratar, nome or "")
    return re.sub(r"\s+", " ", limpo).strip(), parentesco, liberacao


def carregar(nome):
    p = DADOS / f"{nome}.json"
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else []


def s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def b(v) -> bool:
    return v in (-1, 1, True, "-1", "1", "True", "true")


def data_hora(data, hora):
    """Combina data (dd/mm/aaaa ou ISO) e hora (HH:MM, possivelmente com data junto)."""
    data, hora = s(data), s(hora)
    d = None
    for fmt, tam in (("%d/%m/%Y", 10), ("%Y-%m-%d", 10), ("%d/%m/%y", 8)):
        try:
            d = datetime.strptime(data[:tam], fmt)
            break
        except ValueError:
            continue
    if d is None:
        return None
    import re
    m = re.search(r"(\d{1,2}):(\d{2})", hora)
    if m:
        d = d.replace(hour=int(m.group(1)), minute=int(m.group(2)))
    return d

def importar_unidades(db):
    vistos, n = set(), 0
    for r in carregar("tblMoradores"):
        apto = s(r.get("Bloco/Apto")).upper()
        if not apto or apto in vistos:
            if apto:
                print(f"  ! duplicada ignorada: {apto}")
            continue
        bloco_num = apto.partition("/")[0]
        if bloco_num in ("16", "17", "18"):
            continue
        vistos.add(apto)
        eh_inq = b(r.get("Inquilino"))
        inq_nome = inq_cpf = inq_rg = inq_tel = ""
        if eh_inq and s(r.get("Nome")):
            inq_nome, _, _ = extrair_obs(s(r.get("Nome")))
            inq_cpf = s(r.get("CPF 1"))
            inq_rg = s(r.get("RG 1"))
            inq_tel = s(r.get("Telefone 1"))
        u = Unidade(
            bloco_apto=apto, ativo=True, inquilino=eh_inq,
            proprietario=s(r.get("Proprietário")).upper(), cpf=s(r.get("CPF")), rg=s(r.get("RG")),
            telefone=s(r.get("Telefone")), tel_residencial=s(r.get("Tel Residencial")),
            email=s(r.get("E-Mail")), observacoes=s(r.get("Observações")),
            inquilino_nome=inq_nome.upper(), inquilino_cpf=inq_cpf, inquilino_rg=inq_rg, inquilino_telefone=inq_tel,
            senha=s(r.get("Senha")), panico=s(r.get("Pânico")), entrada_senha=s(r.get("Entradasenha")),
            entrada_panico=s(r.get("EntradaPânico")), numero_vaga=s(r.get("Número da Vaga")),
            piso=s(r.get("Piso")), cobertura=b(r.get("Cobertura")), pne=b(r.get("PNE")), pcd=b(r.get("PCD")),
            interfonar_1=s(r.get("Interfonar")), interfonar_2=s(r.get("Interfonar 2")),
            interfonar_3=s(r.get("Interfonar 3")), interfonar_4=s(r.get("Interfonar 4")),
            legado=r,
        )
        # Moradores/inquilinos: Nome, Nome 2..4 com CPF/RG/Telefone 1..4
        for i, suf in enumerate(["", " 2", " 3", " 4"], start=1):
            if eh_inq and i == 1:
                continue
            nome = s(r.get("Nome" + suf))
            if nome:
                nome, par, lib = extrair_obs(nome)
                u.pessoas.append(Pessoa(tipo="MORADOR", nome=nome.upper(), cpf=s(r.get(f"CPF {i}")),
                                        rg=s(r.get(f"RG {i}")), telefone=s(r.get(f"Telefone {i}")),
                                        parentesco=par, liberacao=lib))
        # Autorizados 1..3 -> CPF 5..7 / Telefone 5..7 ; Diarista -> CPF 8 / Telefone 8
        for tipo, col, k in [("AUTORIZADO", "Autorizados(as)", 5), ("AUTORIZADO", "Autorizados 2", 6),
                             ("AUTORIZADO", "Autorizados 3", 7), ("DIARISTA", "Diarista", 8)]:
            nome = s(r.get(col))
            if nome:
                nome, par, lib = extrair_obs(nome)
                u.pessoas.append(Pessoa(tipo=tipo, nome=nome, cpf=s(r.get(f"CPF {k}")),
                                        telefone=s(r.get(f"Telefone {k}")), parentesco=par, liberacao=lib))
        for suf in ["", " 2", " 3"]:
            if s(r.get("Veículo" + suf)) or s(r.get("Placa" + suf)):
                u.veiculos.append(Veiculo(modelo=s(r.get("Veículo" + suf)), cor=s(r.get("Cor" + suf)),
                                          placa=s(r.get("Placa" + suf)).upper()))
        db.add(u)
        n += 1
    return n


def importar_registros(db):
    n = 0
    for r in carregar("tblVisitantes"):
        tipo = "PRESTADOR" if s(r.get("TIPO (P OU V)")).upper().startswith("P") else "VISITANTE"
        db.add(Registro(
            tipo=tipo, entrada=data_hora(r.get("Data"), r.get("Hora Entrada")) or datetime(2025, 1, 1),
            bloco_apto=s(r.get("Bloco/Apto")).upper(), nome=s(r.get("Nome")), cpf=s(r.get("CPF")),
            rg=s(r.get("RG")), veiculo=s(r.get("VEICULO")), placa=s(r.get("PLACA")).upper(),
            autorizado_por=s(r.get("AUTORIZADO POR")), observacoes=s(r.get("OBSERVAÇÕES")),
            empresa=s(r.get("Empresa")), registrado_por="importado"))
        n += 1
    for r in carregar("tblEntregas"):
        db.add(Registro(
            tipo="ENTREGA", entrada=data_hora(r.get("Data de Início"), r.get("Hora Entrada")) or datetime(2025, 1, 1),
            saida=data_hora(r.get("Data do Término"), ""), bloco_apto=s(r.get("Bloco/Apto")).upper(),
            nome=s(r.get("Nome")), cpf=s(r.get("CPF")), rg=s(r.get("RG")), empresa=s(r.get("Empresa")),
            veiculo=s(r.get("Veículo")), placa=s(r.get("Placa")).upper(), telefone=s(r.get("Telefone")),
            registrado_por="importado"))
        n += 1
    return n


def main():
    Base.metadata.create_all(engine)
    garantir_colunas()
    with SessionLocal() as db:
        if "--limpar" in sys.argv:
            for m in (Registro, Pessoa, Veiculo, Unidade):
                db.execute(delete(m))
        elif db.query(Unidade).count():
            sys.exit("O banco já tem unidades. Use --limpar para substituir os dados importados.")
        nu = importar_unidades(db)
        nr = importar_registros(db)
        db.commit()
    print(f"Importadas {nu} unidades e {nr} registros.")


if __name__ == "__main__":
    main()
