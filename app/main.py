import re
from contextlib import asynccontextmanager
from datetime import datetime, time, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.sessions import SessionMiddleware

from . import config
from .database import Base, SessionLocal, engine, garantir_colunas, get_db
from .models import (LIBERACOES, PARENTESCOS, TIPOS_PESSOA, TIPOS_REGISTRO, Pessoa, Registro, Unidade, Usuario,
                     Veiculo)
from .security import hash_senha, verificar_senha

APTOS_PADRAO = [f"{andar}0{num}" for andar in range(1, 5) for num in range(1, 5)]
BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
templates.env.globals.update(TIPOS_REGISTRO=TIPOS_REGISTRO, TIPOS_PESSOA=TIPOS_PESSOA,
                             PARENTESCOS=PARENTESCOS, LIBERACOES=LIBERACOES, APTOS_PADRAO=APTOS_PADRAO)

# Quantidade de linhas no formulário de cada unidade
SLOTS_PESSOAS = [("MORADOR", 4), ("AUTORIZADO", 3), ("DIARISTA", 1)]
SLOTS_VEICULOS = 3
MAX_LINHAS = 6
APTOS_PADRAO = [f"{andar}0{num}" for andar in range(1, 5) for num in range(1, 5)]  # máximo de moradores, autorizados, diaristas e veículos por unidade


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    garantir_colunas()
    with SessionLocal() as db:
        if not db.scalar(select(func.count(Usuario.id))):
            db.add(Usuario(username=config.ADMIN_USER.lower(), nome="Administrador",
                           senha_hash=hash_senha(config.ADMIN_PASSWORD), admin=True))
            db.commit()
    yield


import json as _json
import time as _time

app = FastAPI(title="Portaria UNIARTE", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, same_site="lax",
                   https_only=config.COOKIE_SECURE, max_age=60 * 60 * 24 * 30)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

TEMPO_PERSISTENCIA_FECHADO = 3600  # 1 hora (em segundos) após fechar o programa


def _arq_sessao_local() -> Path:
    return Path.cwd() / ".sessao_ativa.json"


def _eh_local(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1", "localhost", "testclient")


def _salvar_sessao_local(uid: int):
    try:
        _arq_sessao_local().write_text(_json.dumps({"uid": uid, "ts": _time.time()}), encoding="utf-8")
    except Exception:
        pass


def _ler_sessao_local() -> int | None:
    arq = _arq_sessao_local()
    if not arq.exists():
        return None
    try:
        d = _json.loads(arq.read_text(encoding="utf-8"))
        uid = d.get("uid")
        ts = float(d.get("ts") or 0)
        if uid and (_time.time() - ts) <= TEMPO_PERSISTENCIA_FECHADO:
            return int(uid)
        arq.unlink(missing_ok=True)
    except Exception:
        pass
    return None


def _limpar_sessao_local():
    try:
        _arq_sessao_local().unlink(missing_ok=True)
    except Exception:
        pass


# ---------------------------------------------------------------- autenticação
class NaoAutenticado(Exception):
    pass


class SemPermissao(Exception):
    pass


@app.exception_handler(NaoAutenticado)
async def _nao_auth(request: Request, exc: NaoAutenticado):
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(SemPermissao)
async def _sem_perm(request: Request, exc: SemPermissao):
    return HTMLResponse("Acesso restrito a administradores.", status_code=403)


def usuario_atual(request: Request, db: Session = Depends(get_db)) -> Usuario:
    uid = request.session.get("uid")
    if not uid and _eh_local(request):
        uid = _ler_sessao_local()
        if uid:
            request.session["uid"] = uid
    user = db.get(Usuario, uid) if uid else None
    if not user or not user.ativo:
        raise NaoAutenticado()
    if _eh_local(request):
        _salvar_sessao_local(user.id)
    return user


def admin_requerido(user: Usuario = Depends(usuario_atual)) -> Usuario:
    if not user.admin:
        raise SemPermissao()
    return user


def render(request: Request, nome: str, user: Usuario | None = None, **ctx):
    ctx["user"] = user
    return templates.TemplateResponse(request, nome, ctx)


_tentativas: dict[str, list[datetime]] = {}


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, db: Session = Depends(get_db)):
    uid = request.session.get("uid") or (_ler_sessao_local() if _eh_local(request) else None)
    if uid:
        user = db.get(Usuario, uid)
        if user and user.ativo:
            request.session["uid"] = user.id
            if _eh_local(request):
                _salvar_sessao_local(user.id)
            return RedirectResponse("/", status_code=303)
    return render(request, "login.html", erro=None)


@app.post("/login")
def login(request: Request, username: str = Form(...), senha: str = Form(...),
          db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "?"
    agora = datetime.now()
    recentes = [t for t in _tentativas.get(ip, []) if agora - t < timedelta(minutes=10)]
    if len(recentes) >= 8:
        return render(request, "login.html", erro="Muitas tentativas. Aguarde alguns minutos.")
    user = db.scalar(select(Usuario).where(Usuario.username == username.strip().lower()))
    if not user or not user.ativo or not verificar_senha(senha, user.senha_hash):
        _tentativas[ip] = recentes + [agora]
        return render(request, "login.html", erro="Usuário ou senha inválidos.")
    _tentativas.pop(ip, None)
    request.session.clear()
    request.session["uid"] = user.id
    if _eh_local(request):
        _salvar_sessao_local(user.id)
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    if _eh_local(request):
        _limpar_sessao_local()
    return RedirectResponse("/login", status_code=303)


@app.post("/api/sessao/manter")
def api_manter_sessao(user: Usuario = Depends(usuario_atual)):
    return {"ok": True}


# ------------------------------------------------------------------- painel
@app.get("/", response_class=HTMLResponse)
def painel(request: Request, user: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    hoje = datetime.combine(config.agora().date(), time.min)
    por_tipo = dict(db.execute(
        select(Registro.tipo, func.count(Registro.id)).where(Registro.entrada >= hoje)
        .group_by(Registro.tipo)).all())
    dentro = db.scalars(select(Registro).where(Registro.saida.is_(None), Registro.tipo != "ENTREGA")
                        .order_by(Registro.entrada.desc()).limit(50)).all()
    ultimos = db.scalars(select(Registro).order_by(Registro.entrada.desc()).limit(10)).all()
    return render(request, "painel.html", user, por_tipo=por_tipo, dentro=dentro, ultimos=ultimos,
                  total_unidades=db.scalar(select(func.count(Unidade.id))),
                  total_hoje=sum(por_tipo.values()), pagina="painel")


# ------------------------------------------------------------------ unidades
@app.get("/unidades", response_class=HTMLResponse)
def unidades(request: Request, q: str = "", bloco: str = "", apto: str = "",
             user: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    stmt = select(Unidade).options(selectinload(Unidade.pessoas), selectinload(Unidade.veiculos))
    bloco = bloco.strip()
    apto = apto.strip()
    q_str = q.strip()
    if bloco and apto:
        stmt = stmt.where(Unidade.bloco_apto == f"{bloco}/{apto}")
    elif bloco:
        stmt = stmt.where(Unidade.bloco_apto.startswith(f"{bloco}/"))
    elif apto:
        stmt = stmt.where(Unidade.bloco_apto.endswith(f"/{apto}"))
    if q_str:
        like = f"%{q_str}%"
        sub_p = select(Pessoa.unidade_id).where(or_(Pessoa.nome.ilike(like), Pessoa.cpf.ilike(like)))
        sub_v = select(Veiculo.unidade_id).where(Veiculo.placa.ilike(like))
        stmt = stmt.where(or_(Unidade.proprietario.ilike(like), Unidade.cpf.ilike(like),
                              Unidade.inquilino_nome.ilike(like), Unidade.inquilino_cpf.ilike(like),
                              Unidade.id.in_(sub_p), Unidade.id.in_(sub_v)))
    lista = db.scalars(stmt.order_by(Unidade.bloco_apto)).all()
    aptos_padrao = APTOS_PADRAO
    por_chave = {u.bloco_apto: u for u in lista}
    blocos_condominio: dict[str, list[tuple[str, Unidade | None]]] = {}
    for n in range(1, 16):
        b = f"{n:02d}"
        if bloco and b != bloco:
            continue
        if q_str:
            itens = [(u.bloco_apto.partition("/")[2], u) for u in lista if u.bloco_apto.startswith(b + "/")]
        elif apto:
            itens = [(apto, por_chave.get(f"{b}/{apto}"))]
        else:
            extras = [u.bloco_apto.partition("/")[2] for u in lista
                      if u.bloco_apto.startswith(b + "/") and u.bloco_apto.partition("/")[2] not in aptos_padrao]
            itens = [(a, por_chave.get(f"{b}/{a}")) for a in (aptos_padrao + extras)]
        blocos_condominio[b] = itens
    blocos_lista = [f"{n:02d}" for n in range(1, 16)]
    return render(request, "unidades.html", user, lista=lista, blocos=blocos_condominio,
                  blocos_lista=blocos_lista, q=q, bloco=bloco, apto=apto, pagina="unidades")


def _so_se_valido(valor, permitidos) -> str:
    valor = (valor or "").strip()
    return valor if valor in permitidos else ""


def _bool(v) -> bool:
    return v in ("on", "1", "true", "True")


@app.get("/unidades/nova", response_class=HTMLResponse)
def unidade_nova(request: Request, bloco_apto: str = "", user: Usuario = Depends(usuario_atual)):
    u = Unidade(ativo=True, bloco_apto=bloco_apto.strip().upper())
    return render(request, "unidade_form.html", user, u=u, pessoas=_slots_pessoas(None),
                  veiculos=_slots_veiculos(None), pagina="unidades", erro=None)


def _slots_pessoas(u: Unidade | None):
    out = {}
    for tipo, n in SLOTS_PESSOAS:
        existentes = [p for p in (u.pessoas if u else []) if p.tipo == tipo]
        out[tipo] = (existentes + [None] * n)[:max(n, len(existentes))]
    return out


def _slots_veiculos(u: Unidade | None):
    ex = list(u.veiculos) if u else []
    return (ex + [None] * SLOTS_VEICULOS)[:max(SLOTS_VEICULOS, len(ex))]


@app.get("/unidades/{uid}", response_class=HTMLResponse)
def unidade_editar(uid: int, request: Request, user: Usuario = Depends(usuario_atual),
                   db: Session = Depends(get_db)):
    u = db.get(Unidade, uid)
    if not u:
        return RedirectResponse("/unidades", status_code=303)
    return render(request, "unidade_form.html", user, u=u, pessoas=_slots_pessoas(u),
                  veiculos=_slots_veiculos(u), pagina="unidades", erro=None)


CAMPOS_TEXTO_UNIDADE = ["bloco_apto", "proprietario", "cpf", "rg", "telefone", "tel_residencial", "email",
                        "observacoes", "senha", "panico", "entrada_senha", "entrada_panico",
                        "numero_vaga", "piso", "interfonar_1", "interfonar_2", "interfonar_3",
                        "interfonar_4", "inquilino_nome", "inquilino_cpf", "inquilino_rg", "inquilino_telefone", "inquilino_tel_residencial", "inquilino_email", "inquilino_observacoes"]
CAMPOS_BOOL_UNIDADE = ["ativo", "inquilino", "cobertura", "pne", "pcd"]


@app.post("/unidades/salvar")
async def unidade_salvar(request: Request, user: Usuario = Depends(usuario_atual),
                         db: Session = Depends(get_db)):
    f = await request.form()
    uid = f.get("id")
    u = db.get(Unidade, int(uid)) if uid else Unidade()
    for c in CAMPOS_TEXTO_UNIDADE:
        setattr(u, c, (f.get(c) or "").strip())
    u.bloco_apto, u.proprietario, u.inquilino_nome = u.bloco_apto.upper(), u.proprietario.upper(), u.inquilino_nome.upper()
    for c in CAMPOS_BOOL_UNIDADE:
        setattr(u, c, _bool(f.get(c)))

    u.pessoas.clear()
    for tipo, n in SLOTS_PESSOAS:
        for i in range(MAX_LINHAS):
            nome = (f.get(f"p_{tipo}_{i}_nome") or "").strip().upper()
            if nome:
                u.pessoas.append(Pessoa(tipo=tipo, nome=nome,
                                        cpf=(f.get(f"p_{tipo}_{i}_cpf") or "").strip(),
                                        rg=(f.get(f"p_{tipo}_{i}_rg") or "").strip(),
                                        telefone=(f.get(f"p_{tipo}_{i}_telefone") or "").strip(),
                                        parentesco=_so_se_valido(f.get(f"p_{tipo}_{i}_parentesco"), PARENTESCOS),
                                        liberacao=_so_se_valido(f.get(f"p_{tipo}_{i}_liberacao"), LIBERACOES)))
    u.veiculos.clear()
    for i in range(MAX_LINHAS):
        modelo = (f.get(f"v_{i}_modelo") or "").strip()
        placa = (f.get(f"v_{i}_placa") or "").strip().upper()
        if modelo or placa:
            u.veiculos.append(Veiculo(modelo=modelo, placa=placa, cor=(f.get(f"v_{i}_cor") or "").strip()))

    duplicada = db.scalar(select(Unidade.id).where(Unidade.bloco_apto == u.bloco_apto, Unidade.id != (u.id or 0)))
    erro = None
    if not re.fullmatch(r"(0[1-9]|1[0-5])/\d{3}", u.bloco_apto):
        erro = "Informe o Bloco/Apto no formato 00/000 (bloco de 01 a 15)."
    elif duplicada:
        erro = "Já existe uma unidade com esse Bloco/Apto."
    elif not u.proprietario or not u.cpf:
        erro = "Preencha Nome e CPF do Proprietário antes de finalizar o cadastro."
    elif u.inquilino and (not u.inquilino_nome or not u.inquilino_cpf):
        erro = "Preencha Nome e CPF do Inquilino antes de finalizar o cadastro."

    if erro:
        db.expunge_all()
        return render(request, "unidade_form.html", user, u=u, pessoas=_slots_pessoas(u),
                      veiculos=_slots_veiculos(u), pagina="unidades", erro=erro)

    db.add(u)
    db.commit()
    return RedirectResponse("/unidades", status_code=303)


@app.post("/unidades/{uid}/excluir")
def unidade_excluir(uid: int, user: Usuario = Depends(admin_requerido), db: Session = Depends(get_db)):
    u = db.get(Unidade, uid)
    if u:
        db.delete(u)
        db.commit()
    return RedirectResponse("/unidades", status_code=303)


# ----------------------------------------------------------------- registros
def _parse_data(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


@app.get("/registros", response_class=HTMLResponse)
def registros(request: Request, q: str = "", tipo: str = "", de: str = "", ate: str = "",
              apenas_abertos: str = "", pg: int = 1, user: Usuario = Depends(usuario_atual),
              db: Session = Depends(get_db)):
    stmt = select(Registro)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Registro.nome.ilike(like), Registro.cpf.ilike(like),
                              Registro.bloco_apto.ilike(like), Registro.placa.ilike(like),
                              Registro.empresa.ilike(like)))
    if tipo in TIPOS_REGISTRO:
        stmt = stmt.where(Registro.tipo == tipo)
    d1, d2 = _parse_data(de), _parse_data(ate)
    if d1:
        stmt = stmt.where(Registro.entrada >= d1)
    if d2:
        stmt = stmt.where(Registro.entrada < d2 + timedelta(days=1))
    if apenas_abertos:
        stmt = stmt.where(Registro.saida.is_(None))
    por_pg = 50
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    lista = db.scalars(stmt.order_by(Registro.entrada.desc()).limit(por_pg).offset((max(pg, 1) - 1) * por_pg)).all()
    return render(request, "registros.html", user, lista=lista, q=q, tipo=tipo, de=de, ate=ate,
                  apenas_abertos=apenas_abertos, pg=pg, total=total, por_pg=por_pg, pagina="registros")


def _mapa_blocos(db: Session) -> dict[str, list[str]]:
    """{'01': ['101', ..., '404'], ...} com todos os blocos (01-15) e apartamentos (101-404)."""
    mapa: dict[str, list[str]] = {f"{n:02d}": list(APTOS_PADRAO) for n in range(1, 16)}
    for ba in db.scalars(select(Unidade.bloco_apto).order_by(Unidade.bloco_apto)).all():
        bloco, _, apto = ba.partition("/")
        lista = mapa.setdefault(bloco, [])
        if apto and apto not in lista:
            lista.append(apto)
    return mapa


@app.get("/registros/novo", response_class=HTMLResponse)
def registro_novo(request: Request, tipo: str = "VISITANTE", user: Usuario = Depends(usuario_atual),
                  db: Session = Depends(get_db)):
    porteiro = user.nome or user.username
    r = Registro(tipo=tipo if tipo in TIPOS_REGISTRO else "VISITANTE", entrada=config.agora(), autorizado_por=porteiro)
    blocos = _mapa_blocos(db)
    return render(request, "registro_form.html", user, r=r, blocos=blocos, pagina="registros", erro=None)


@app.get("/registros/{rid}", response_class=HTMLResponse)
def registro_editar(rid: int, request: Request, user: Usuario = Depends(usuario_atual),
                    db: Session = Depends(get_db)):
    r = db.get(Registro, rid)
    if not r:
        return RedirectResponse("/registros", status_code=303)
    blocos = _mapa_blocos(db)
    return render(request, "registro_form.html", user, r=r, blocos=blocos, pagina="registros", erro=None)


@app.post("/registros/salvar")
async def registro_salvar(request: Request, user: Usuario = Depends(usuario_atual),
                          db: Session = Depends(get_db)):
    f = await request.form()
    rid = f.get("id")
    porteiro = user.nome or user.username
    r = db.get(Registro, int(rid)) if rid else Registro(registrado_por=user.username, autorizado_por=porteiro)
    r.tipo = f.get("tipo") if f.get("tipo") in TIPOS_REGISTRO else "VISITANTE"
    for c in ["bloco_apto", "nome", "cpf", "rg", "telefone", "empresa", "veiculo", "placa", "observacoes"]:
        setattr(r, c, (f.get(c) or "").strip())
    if not r.autorizado_por:
        r.autorizado_por = porteiro
    r.bloco_apto, r.placa, r.nome = r.bloco_apto.upper(), r.placa.upper(), r.nome.upper()
    for campo in ("entrada", "saida"):
        try:
            setattr(r, campo, datetime.strptime(f.get(campo) or "", "%Y-%m-%dT%H:%M"))
        except ValueError:
            setattr(r, campo, config.agora() if campo == "entrada" else None)
    if not r.bloco_apto or not r.nome or not r.cpf:
        db.expunge_all()
        return render(request, "registro_form.html", user, r=r, blocos=_mapa_blocos(db),
                      pagina="registros", erro="Preencha Bloco/Apto, Nome e CPF antes de finalizar o cadastro.")
    db.add(r)
    db.commit()
    return RedirectResponse("/registros", status_code=303)


@app.post("/registros/{rid}/saida")
def registro_saida(rid: int, request: Request, user: Usuario = Depends(usuario_atual),
                   db: Session = Depends(get_db)):
    r = db.get(Registro, rid)
    if r and not r.saida:
        r.saida = config.agora()
        db.commit()
    return RedirectResponse(request.headers.get("referer") or "/registros", status_code=303)


@app.post("/registros/{rid}/excluir")
def registro_excluir(rid: int, request: Request, user: Usuario = Depends(admin_requerido), db: Session = Depends(get_db)):
    r = db.get(Registro, rid)
    if r:
        db.delete(r)
        db.commit()
    return RedirectResponse("/registros", status_code=303)


@app.get("/api/unidade/{bloco_apto:path}")
def api_unidade(bloco_apto: str, user: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Usado pelo formulário de registro e pelo popup de consulta rápida da unidade."""
    u = db.scalar(select(Unidade).where(Unidade.bloco_apto == bloco_apto.upper())
                  .options(selectinload(Unidade.pessoas), selectinload(Unidade.veiculos)))
    if not u:
        return {"encontrada": False}
    return {
        "encontrada": True, "id": u.id, "bloco_apto": u.bloco_apto, "ativo": u.ativo,
        "inquilino": u.inquilino, "proprietario": u.proprietario, "cpf": u.cpf,
        "inquilino_nome": u.inquilino_nome, "inquilino_cpf": u.inquilino_cpf, "inquilino_rg": u.inquilino_rg,
        "inquilino_telefone": u.inquilino_telefone, "inquilino_tel_residencial": u.inquilino_tel_residencial,
        "inquilino_email": u.inquilino_email, "inquilino_observacoes": u.inquilino_observacoes,
        "telefone": u.telefone, "tel_residencial": u.tel_residencial, "observacoes": u.observacoes,
        "numero_vaga": u.numero_vaga, "piso": u.piso,
        "interfonar": [x for x in (u.interfonar_1, u.interfonar_2, u.interfonar_3, u.interfonar_4) if x],
        "pessoas": [{"nome": p.nome, "tipo": p.tipo, "cpf": p.cpf, "telefone": p.telefone,
                     "parentesco": p.parentesco, "liberacao": p.liberacao} for p in u.pessoas],
        "veiculos": [{"modelo": v.modelo, "cor": v.cor, "placa": v.placa} for v in u.veiculos],
    }


# ------------------------------------------------------------------ usuários
@app.get("/usuarios", response_class=HTMLResponse)
def usuarios(request: Request, user: Usuario = Depends(admin_requerido), db: Session = Depends(get_db)):
    lista = db.scalars(select(Usuario).order_by(Usuario.username)).all()
    return render(request, "usuarios.html", user, lista=lista, pagina="usuarios", erro=None)


@app.post("/usuarios/salvar")
def usuario_salvar(request: Request, username: str = Form(...), nome: str = Form(""),
                   senha: str = Form(""), admin: str = Form(""), ativo: str = Form(""),
                   id: str = Form(""), user: Usuario = Depends(admin_requerido),
                   db: Session = Depends(get_db)):
    username = username.strip().lower()
    alvo = db.get(Usuario, int(id)) if id else None
    outro = db.scalar(select(Usuario).where(Usuario.username == username, Usuario.id != (alvo.id if alvo else 0)))
    if outro or not username or (not alvo and len(senha) < 6) or (senha and len(senha) < 6):
        lista = db.scalars(select(Usuario).order_by(Usuario.username)).all()
        return render(request, "usuarios.html", user, lista=lista, pagina="usuarios",
                      erro="Usuário inválido/duplicado ou senha com menos de 6 caracteres.")
    alvo = alvo or Usuario()
    alvo.username, alvo.nome = username, nome.strip().upper()
    alvo.admin, alvo.ativo = _bool(admin), _bool(ativo)
    if alvo.id == user.id:  # não permite se bloquear
        alvo.admin, alvo.ativo = True, True
    if senha:
        alvo.senha_hash = hash_senha(senha)
    db.add(alvo)
    db.commit()
    return RedirectResponse("/usuarios", status_code=303)


# --------------------------------------------------------------- atualizações
@app.get("/api/atualizacoes/verificar")
def api_verificar_atualizacoes(forcar: bool = False, user: Usuario = Depends(usuario_atual)):
    from .updater import consultar_status_remoto
    st = consultar_status_remoto(timeout=5.0, forcar=forcar)
    if not user.admin:
        st["commit_mensagem"] = ""
    return st


@app.post("/api/atualizacoes/aplicar-codigo")
def api_aplicar_codigo(user: Usuario = Depends(usuario_atual)):
    from .updater import aplicar_atualizacao_codigo
    return aplicar_atualizacao_codigo()


@app.post("/api/atualizacoes/baixar-instalador")
def api_baixar_instalador(url: str = Form(""), versao: str = Form(""), user: Usuario = Depends(usuario_atual)):
    from .updater import baixar_e_executar_instalador, consultar_status_remoto
    if not url:
        st = consultar_status_remoto(timeout=6.0)
        url = st.get("instalador_url", "")
        versao = st.get("versao_instalador_remota", "")
    return baixar_e_executar_instalador(url, versao)


@app.post("/api/atualizacoes/reiniciar")
def api_reiniciar_sistema(user: Usuario = Depends(usuario_atual)):
    _salvar_sessao_local(user.id)
    from .updater import reiniciar_aplicativo
    return reiniciar_aplicativo()
