from decimal import Decimal

from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.infrastructure.database import Base, engine, get_db
from app.infrastructure import models  # noqa: F401 (registra as tabelas)
from app.application.create_order import create_order
from app.application.process_payment import process_payment
from app.domain.entities import ItemPedido
from app.domain.enums import CanalPedido, StatusPedido
from app.domain.exceptions import (
    DomainError, NaoEncontrado, EstoqueInsuficiente, ProdutoIndisponivel
)
from app.infrastructure.models.order import Order
from app.infrastructure.models.order_item import OrderItem
from app.infrastructure.models.product_ingredient import ProductIngredient
from app.infrastructure.models.stock import Stock
from app.infrastructure.models.user import User
from app.infrastructure.security import (
    verificar_senha, criar_token, verificar_perfil
)

Base.metadata.create_all(bind=engine)
app = FastAPI(title="API Rede Raízes do Nordeste")

# ---------------------------- Padrão de erro ----------------------------

CODIGOS_ERRO = {
    400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN",
    404: "NOT_FOUND", 409: "CONFLICT", 422: "VALIDATION_ERROR",
    500: "INTERNAL_ERROR",
}


def montar_erro(request, status, mensagem, detalhes=None, headers=None):
    corpo = {
        "status": status,
        "erro": CODIGOS_ERRO.get(status, "ERROR"),
        "mensagem": mensagem,
        "caminho": request.url.path,
    }
    if detalhes:
        corpo["detalhes"] = detalhes
    return JSONResponse(status_code=status, content=corpo, headers=headers)


@app.exception_handler(StarletteHTTPException)
async def tratar_http(request: Request, exc: StarletteHTTPException):
    return montar_erro(request, exc.status_code, str(exc.detail),
                       headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def tratar_validacao(request: Request, exc: RequestValidationError):
    detalhes = [
        {"campo": ".".join(str(p) for p in e["loc"] if p != "body"),
         "mensagem": e["msg"]}
        for e in exc.errors()
    ]
    return montar_erro(request, 422, "Dados inválidos.", detalhes)


@app.exception_handler(Exception)
async def tratar_erro_interno(request: Request, exc: Exception):
    return montar_erro(request, 500, "Erro interno do servidor.")


def erro_dominio(erro: Exception, padrao: int = 400) -> HTTPException:
    """Converte erros de domínio em HTTPException."""
    if isinstance(erro, NaoEncontrado):
        return HTTPException(404, str(erro))
    if isinstance(erro, (EstoqueInsuficiente, ProdutoIndisponivel)):
        return HTTPException(409, str(erro))
    return HTTPException(padrao, str(erro))


ERROS_DOMINIO = (DomainError, NaoEncontrado,
                 EstoqueInsuficiente, ProdutoIndisponivel)

# ------------------------------ Schemas ---------------------------------


class ItemPedidoEntrada(BaseModel):
    id_produto: int
    quantidade: int = Field(gt=0)
    preco_unitario: Decimal


class PedidoEntrada(BaseModel):
    id_unidade: int
    canal_pedido: CanalPedido
    chave_idempotencia: str
    itens: list[ItemPedidoEntrada] = Field(min_length=1)
    id_usuario: int | None = None
    id_atendente: int | None = None


class AtualizarStatusEntrada(BaseModel):
    status: str


class CancelarPedidoEntrada(BaseModel):
    motivo: str


class PagamentoEntrada(BaseModel):
    tipo: str
    aprovado: bool = True
    falha_gateway: bool = False  # true = gateway fora do ar (PENDENTE)


class LoginEntrada(BaseModel):
    email: str
    senha: str

# ------------------------- Regras de acesso (RN08) -----------------------

PERMISSAO_STATUS = {
    "COZINHA": {"EM_PREPARO", "PRONTO"},
    "ATENDENTE": {"RETIRADO"},
    "GERENTE": {"EM_PREPARO", "PRONTO", "RETIRADO"},
}

TRANSICOES = {
    "PAGO": ["EM_PREPARO"],
    "EM_PREPARO": ["PRONTO"],
    "PRONTO": ["RETIRADO"],
}


def pode_acessar_pedido(pedido: Order, usuario: User) -> bool:
    if usuario.role == "MATRIZ":
        return True
    if usuario.role == "CLIENTE":
        return pedido.user_id == usuario.id
    return pedido.unit_id == usuario.unit_id


def buscar_pedido_autorizado(db: Session, pedido_id: int, usuario: User) -> Order:
    pedido = db.get(Order, pedido_id)
    if pedido is None:
        raise HTTPException(404, "Pedido não encontrado.")
    if not pode_acessar_pedido(pedido, usuario):
        raise HTTPException(
            403, "Usuário sem permissão para acessar este pedido.")
    return pedido


def resumo(p: Order) -> dict:
    return {"id": p.id, "unidade": p.unit_id, "canal": p.order_channel,
            "status": p.status, "valor_total": p.total_amount}

# ------------------------------ Endpoints -------------------------------


@app.get("/")
def home():
    return {"mensagem": "API Rede Raízes do Nordeste funcionando"}


@app.post("/auth/login")
def login(dados: LoginEntrada, db: Session = Depends(get_db)):
    usuario = db.query(User).filter(
        User.email == dados.email, User.active == True  # noqa: E712
    ).first()

    if usuario is None or not verificar_senha(dados.senha, usuario.password_hash):
        raise HTTPException(401, "E-mail ou senha inválidos.")

    token = criar_token({"sub": str(usuario.id), "role": usuario.role,
                         "unit_id": usuario.unit_id})
    return {"access_token": token, "token_type": "bearer",
            "usuario": usuario.name, "perfil": usuario.role}


@app.post("/pedidos", status_code=201)
def cadastrar_pedido(
    dados: PedidoEntrada,
    db: Session = Depends(get_db),
    usuario: User = Depends(verificar_perfil("CLIENTE", "ATENDENTE", "GERENTE")),
):
    if usuario.role == "CLIENTE":
        if dados.canal_pedido == CanalPedido.BALCAO:
            raise HTTPException(
                403, "Cliente não pode criar pedido no canal BALCAO.")
        id_usuario, id_atendente = usuario.id, None
    else:
        if usuario.unit_id != dados.id_unidade:
            raise HTTPException(403, "Usuário sem permissão para esta unidade.")
        id_usuario = dados.id_usuario
        id_atendente = usuario.id if usuario.role == "ATENDENTE" else dados.id_atendente

    try:
        pedido = create_order(
            db=db,
            id_unidade=dados.id_unidade,
            canal_pedido=dados.canal_pedido.value,
            chave_idempotencia=dados.chave_idempotencia,
            itens=[ItemPedido(**i.model_dump()) for i in dados.itens],
            id_usuario=id_usuario,
            id_atendente=id_atendente,
        )
    except ERROS_DOMINIO as erro:
        raise erro_dominio(erro)

    return {**resumo(pedido), "mensagem": "Pedido cadastrado com sucesso."}


@app.get("/pedidos")
def listar_pedidos(
    canal_pedido: CanalPedido | None = None,
    status: StatusPedido | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: User = Depends(verificar_perfil(
        "CLIENTE", "ATENDENTE", "COZINHA", "GERENTE", "MATRIZ")),
):
    consulta = db.query(Order)

    # RN08: cliente vê só os seus; matriz vê a rede; demais, a própria unidade
    if usuario.role == "CLIENTE":
        consulta = consulta.filter(Order.user_id == usuario.id)
    elif usuario.role != "MATRIZ":
        consulta = consulta.filter(Order.unit_id == usuario.unit_id)

    # RF05 / RN02: filtros por canal e status
    if canal_pedido:
        consulta = consulta.filter(Order.order_channel == canal_pedido.value)
    if status:
        consulta = consulta.filter(Order.status == status.value)

    pedidos = (consulta.order_by(Order.id.desc())
               .offset((page - 1) * limit).limit(limit).all())

    return [{**resumo(p), "data_criacao": p.created_at} for p in pedidos]


@app.patch("/pedidos/{pedido_id}/status")
def atualizar_status(
    pedido_id: int,
    dados: AtualizarStatusEntrada,
    db: Session = Depends(get_db),
    usuario: User = Depends(verificar_perfil("COZINHA", "ATENDENTE", "GERENTE")),
):
    pedido = buscar_pedido_autorizado(db, pedido_id, usuario)

    try:
        novo = StatusPedido(dados.status).value
    except ValueError:
        raise HTTPException(400, "Status inválido.")

    if novo not in PERMISSAO_STATUS[usuario.role]:
        raise HTTPException(403, "Perfil sem permissão para definir este status.")
    if novo not in TRANSICOES.get(pedido.status, []):
        raise HTTPException(400, "Transição de status não permitida.")

    pedido.status = novo
    db.commit()
    return {"id": pedido.id, "status": pedido.status,
            "mensagem": "Status atualizado com sucesso."}


@app.patch("/pedidos/{pedido_id}/cancelar")
def cancelar_pedido(
    pedido_id: int,
    dados: CancelarPedidoEntrada,
    db: Session = Depends(get_db),
    usuario: User = Depends(verificar_perfil("CLIENTE", "ATENDENTE", "GERENTE")),
):
    pedido = buscar_pedido_autorizado(db, pedido_id, usuario)
    motivo = dados.motivo.strip()

    if not motivo:
        raise HTTPException(400, "Informe o motivo do cancelamento.")
    if pedido.status not in (StatusPedido.AGUARDANDO_PAGAMENTO.value,
                             StatusPedido.PAGO.value):
        raise HTTPException(400, "Este pedido não pode ser cancelado.")

    try:
        itens = db.query(OrderItem).filter(OrderItem.order_id == pedido.id).all()
        for item in itens:
            receitas = db.query(ProductIngredient).filter(
                ProductIngredient.product_id == item.product_id).all()
            for r in receitas:
                estoque = db.query(Stock).filter(
                    Stock.unit_id == pedido.unit_id,
                    Stock.ingredient_id == r.ingredient_id).first()
                if estoque:
                    estoque.quantity += (Decimal(str(r.quantity))
                                         * Decimal(str(item.quantity)))

        pedido.status = StatusPedido.CANCELADO.value
        pedido.cancellation_reason = motivo
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"id": pedido.id, "status": pedido.status, "motivo": motivo,
            "mensagem": "Pedido cancelado com sucesso."}


MENSAGENS_PAGAMENTO = {
    "APROVADO": "Pagamento aprovado com sucesso.",
    "PENDENTE": "Gateway de pagamento indisponível. "
                "Pagamento pendente, tente novamente.",
    "RECUSADO": "Pagamento recusado.",
}


@app.post("/pedidos/{pedido_id}/pagamento")
def realizar_pagamento(
    pedido_id: int,
    dados: PagamentoEntrada,
    db: Session = Depends(get_db),
    usuario: User = Depends(verificar_perfil("CLIENTE", "ATENDENTE", "GERENTE")),
):
    buscar_pedido_autorizado(db, pedido_id, usuario)  # 404 / 403

    try:
        pg = process_payment(db=db, pedido_id=pedido_id, tipo=dados.tipo,
                             aprovado=dados.aprovado,
                             falha_gateway=dados.falha_gateway)
    except ERROS_DOMINIO as erro:
        raise erro_dominio(erro, padrao=422)

    return {"id": pg.id, "pedido_id": pg.pedido_id, "valor": pg.valor,
            "tipo": pg.tipo, "status": pg.status,
            "mensagem": MENSAGENS_PAGAMENTO.get(pg.status, "Pagamento recusado.")}