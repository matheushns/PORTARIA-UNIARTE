from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import agora
from .database import Base

TIPOS_REGISTRO = {"VISITANTE": "Visitante", "PRESTADOR": "Prestador", "ENTREGA": "Entrega"}
PARENTESCOS = ["PAI", "MÃE", "FILHO(A)", "IRMÃ(O)", "ESPOSO(A)", "PRIMO(A)", "TIO(A)", "VÔ(Ó)",
               "SOGRO(A)", "GENRO", "NORA", "AMIGO(A)"]
LIBERACOES = ["LIBERADO", "NÃO LIBERADO"]
TIPOS_PESSOA = {"MORADOR": "Morador/Inquilino", "AUTORIZADO": "Autorizado", "DIARISTA": "Diarista"}


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    nome: Mapped[str] = mapped_column(String(120), default="")
    senha_hash: Mapped[str] = mapped_column(String(255))
    admin: Mapped[bool] = mapped_column(Boolean, default=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Unidade(Base):
    """Apartamento (antiga tblMoradores). Formato do identificador: BLOCO/APTO, ex. 01/101."""
    __tablename__ = "unidades"
    id: Mapped[int] = mapped_column(primary_key=True)
    bloco_apto: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    inquilino: Mapped[bool] = mapped_column(Boolean, default=False)

    proprietario: Mapped[str] = mapped_column(String(200), default="")
    cpf: Mapped[str] = mapped_column(String(20), default="")
    rg: Mapped[str] = mapped_column(String(30), default="")
    telefone: Mapped[str] = mapped_column(String(40), default="")
    tel_residencial: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    observacoes: Mapped[str] = mapped_column(Text, default="")

    inquilino_nome: Mapped[str] = mapped_column(String(200), default="")
    inquilino_cpf: Mapped[str] = mapped_column(String(20), default="")
    inquilino_rg: Mapped[str] = mapped_column(String(30), default="")
    inquilino_telefone: Mapped[str] = mapped_column(String(40), default="")
    inquilino_tel_residencial: Mapped[str] = mapped_column(String(40), default="")
    inquilino_email: Mapped[str] = mapped_column(String(200), default="")
    inquilino_observacoes: Mapped[str] = mapped_column(Text, default="")

    senha: Mapped[str] = mapped_column(String(60), default="")
    panico: Mapped[str] = mapped_column(String(60), default="")
    entrada_senha: Mapped[str] = mapped_column(String(60), default="")
    entrada_panico: Mapped[str] = mapped_column(String(60), default="")

    numero_vaga: Mapped[str] = mapped_column(String(30), default="")
    piso: Mapped[str] = mapped_column(String(30), default="")
    cobertura: Mapped[bool] = mapped_column(Boolean, default=False)
    pne: Mapped[bool] = mapped_column(Boolean, default=False)
    pcd: Mapped[bool] = mapped_column(Boolean, default=False)

    interfonar_1: Mapped[str] = mapped_column(String(60), default="")
    interfonar_2: Mapped[str] = mapped_column(String(60), default="")
    interfonar_3: Mapped[str] = mapped_column(String(60), default="")
    interfonar_4: Mapped[str] = mapped_column(String(60), default="")

    legado: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # registro original do Access

    pessoas: Mapped[list["Pessoa"]] = relationship(
        back_populates="unidade", cascade="all, delete-orphan", order_by="Pessoa.id"
    )
    veiculos: Mapped[list["Veiculo"]] = relationship(
        back_populates="unidade", cascade="all, delete-orphan", order_by="Veiculo.id"
    )


class Pessoa(Base):
    __tablename__ = "pessoas"
    id: Mapped[int] = mapped_column(primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))
    nome: Mapped[str] = mapped_column(String(200))
    cpf: Mapped[str] = mapped_column(String(20), default="")
    rg: Mapped[str] = mapped_column(String(30), default="")
    telefone: Mapped[str] = mapped_column(String(40), default="")
    parentesco: Mapped[str] = mapped_column(String(20), default="")
    liberacao: Mapped[str] = mapped_column(String(20), default="")
    unidade: Mapped[Unidade] = relationship(back_populates="pessoas")


class Veiculo(Base):
    __tablename__ = "veiculos"
    id: Mapped[int] = mapped_column(primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id", ondelete="CASCADE"), index=True)
    modelo: Mapped[str] = mapped_column(String(80), default="")
    cor: Mapped[str] = mapped_column(String(40), default="")
    placa: Mapped[str] = mapped_column(String(10), default="", index=True)
    unidade: Mapped[Unidade] = relationship(back_populates="veiculos")


class Registro(Base):
    """Entrada de visitante, prestador ou entrega (antigas tblVisitantes e tblEntregas)."""
    __tablename__ = "registros"
    __table_args__ = (Index("ix_registros_entrada", "entrada"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(12), default="VISITANTE")
    entrada: Mapped[datetime] = mapped_column(DateTime, default=agora)
    saida: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    bloco_apto: Mapped[str] = mapped_column(String(20), default="", index=True)
    nome: Mapped[str] = mapped_column(String(200), default="")
    cpf: Mapped[str] = mapped_column(String(20), default="")
    rg: Mapped[str] = mapped_column(String(30), default="")
    telefone: Mapped[str] = mapped_column(String(40), default="")
    empresa: Mapped[str] = mapped_column(String(150), default="")
    veiculo: Mapped[str] = mapped_column(String(80), default="")
    placa: Mapped[str] = mapped_column(String(10), default="")
    autorizado_por: Mapped[str] = mapped_column(String(150), default="")
    observacoes: Mapped[str] = mapped_column(Text, default="")
    registrado_por: Mapped[str] = mapped_column(String(50), default="")
