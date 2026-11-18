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
    DomainError,
    NaoEncontrado,
    EstoqueInsuficiente,
    ProdutoIndisponivel
)
from app.infrastructure.models.order import Order
from app.infrastructure.models.order_item import OrderItem
from app.infrastructure.models.product_ingredient import ProductIngredient
from app.infrastructure.models.stock import Stock
from app.infrastructure.models.user import User
from app.infrastructure.security import (
    verificar_senha,
    criar_token,
    verificar_perfil
)

Base.metadata.create_all(bind=engine)

# Se o seu FastAPI(...) original tinha outro title/description, mantenha o seu.
app = FastAPI(title="API Rede Raízes do Nordeste")


# ---------------------------------------------------------------------------
# Padrão de erro único para toda a API
# ---------------------------------------------------------------------------

CODIGOS_ERRO = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    500: "INTERNAL_ERROR",
}


def montar_erro(request: Request, status: int, mensagem: str,
                detalhes=None, headers=None):
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
    return montar_erro(
        request, exc.status_code, str(exc.detail),
        headers=getattr(exc, "headers", None)
    )


@app.exception_handler(RequestValidationError)
async def tratar_validacao(request: Request, exc: RequestValidationError):
    detalhes = [
        {
            "campo": ".".join(str(p) for p in erro["loc"] if p != "body"),
            "mensagem": erro["msg"],
        }
        for erro in exc.errors()
    ]
    return montar_erro(request, 422, "Dados inválidos.", detalhes)


@app.exception_handler(Exception)
async def tratar_erro_interno(request: Request, exc: Exception):
    return montar_erro(request, 500, "Erro interno do servidor.")


# ---------------------------------------------------------------------------
# Schemas de entrada
# ---------------------------------------------------------------------------

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
    # Simulação de teste: true = gateway fora do ar (pagamento fica PENDENTE)
    falha_gateway: bool = False


class LoginEntrada(BaseModel):
    email: str
    senha: str


# ---------------------------------------------------------------------------
# Regras de acesso (RN08: cada perfil acessa apenas o seu escopo)
# ---------------------------------------------------------------------------

# RF08: cozinha atualiza preparo; atendente registra a retirada
PERMISSAO_STATUS = {
    "COZINHA": {"EM_PREPARO", "PRONTO"},
    "ATENDENTE": {"RETIRADO"},
    "GERENTE": {"EM_PREPARO", "PRONTO", "RETIRADO"},
}

TRANSICOES = {
    "AGUARDANDO_PAGAMENTO": [],
    "PAGO": ["EM_PREPARO"],
    "EM_PREPARO": ["PRONTO"],
    "PRONTO": ["RETIRADO"],
    "RETIRADO": [],
    "CANCELADO": [],
}


def pode_acessar_pedido(pedido: Order, usuario: User) -> bool:
    if usuario.role == "MATRIZ":
        return True
    if usuario.role == "CLIENTE":
        return pedido.user_id == usuario.id
    return pedido.unit_id == usuario.unit_id


def buscar_pedido_autorizado(db: Session, pedido_id: int, usuario: User) -> Order:
    pedido = db.query(Order).filter(Order.id == pedido_id).first()
    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")
    if not pode_acessar_pedido(pedido, usuario):
        raise HTTPException(
            status_code=403,
            detail="Usuário sem permissão para acessar este pedido."
        )
    return pedido


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def home():
    return {"mensagem": "API Rede Raízes do Nordeste funcionando"}


@app.post("/auth/login")
def login(dados: LoginEntrada, db: Session = Depends(get_db)):
    usuario = db.query(User).filter(
        User.email == dados.email,
        User.active == True
    ).first()

    if usuario is None or not verificar_senha(
        dados.senha,
        usuario.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="E-mail ou senha inválidos."
        )

    token = criar_token({
        "sub": str(usuario.id),
        "role": usuario.role,
        "unit_id": usuario.unit_id
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "usuario": usuario.name,
        "perfil": usuario.role
    }


@app.post("/pedidos", status_code=201)
def cadastrar_pedido(
    dados: PedidoEntrada,
    db: Session = Depends(get_db),
    usuario: User = Depends(
        verificar_perfil("CLIENTE", "ATENDENTE", "GERENTE")
    )
):
    if usuario.role == "CLIENTE":
        # Cliente pede para si mesmo e não usa o canal de balcão
        if dados.canal_pedido.value == "BALCAO":
            raise HTTPException(
                status_code=403,
                detail="Cliente não pode criar pedido no canal BALCAO."
            )
        id_usuario = usuario.id
        id_atendente = None
    else:
        # Atendente e gerente só criam pedidos na própria unidade
        if usuario.unit_id != dados.id_unidade:
            raise HTTPException(
                status_code=403,
                detail="Usuário sem permissão para esta unidade."
            )
        id_usuario = dados.id_usuario
        id_atendente = (
            usuario.id if usuario.role == "ATENDENTE"
            else dados.id_atendente
        )

    try:
        itens = [
            ItemPedido(
                id_produto=item.id_produto,
                quantidade=item.quantidade,
                preco_unitario=item.preco_unitario
            )
            for item in dados.itens
        ]

        pedido = create_order(
            db=db,
            id_unidade=dados.id_unidade,
            canal_pedido=dados.canal_pedido.value,
            chave_idempotencia=dados.chave_idempotencia,
            itens=itens,
            id_usuario=id_usuario,
            id_atendente=id_atendente
        )

        return {
            "id": pedido.id,
            "unidade": pedido.unit_id,
            "canal": pedido.order_channel,
            "status": pedido.status,
            "valor_total": pedido.total_amount,
            "mensagem": "Pedido cadastrado com sucesso."
        }

    except NaoEncontrado as erro:
        raise HTTPException(status_code=404, detail=str(erro))
    except (EstoqueInsuficiente, ProdutoIndisponivel) as erro:
        raise HTTPException(status_code=409, detail=str(erro))
    except DomainError as erro:
        raise HTTPException(status_code=400, detail=str(erro))


@app.get("/pedidos")
def listar_pedidos(
    canal_pedido: CanalPedido | None = None,
    status: StatusPedido | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: User = Depends(verificar_perfil(
        "CLIENTE", "ATENDENTE", "COZINHA", "GERENTE", "MATRIZ"
    ))
):
    consulta = db.query(Order)

    # RN08: cliente vê só os seus; matriz vê a rede; demais, a própria unidade
    if usuario.role == "CLIENTE":
        consulta = consulta.filter(Order.user_id == usuario.id)
    elif usuario.role != "MATRIZ":
        consulta = consulta.filter(Order.unit_id == usuario.unit_id)

    # RF05 / RN02: filtros por canal de origem e status
    if canal_pedido:
        consulta = consulta.filter(
            Order.order_channel == canal_pedido.value
        )
    if status:
        consulta = consulta.filter(Order.status == status.value)

    pedidos = (
        consulta.order_by(Order.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    return [
        {
            "id": pedido.id,
            "unidade": pedido.unit_id,
            "canal": pedido.order_channel,
            "status": pedido.status,
            "valor_total": pedido.total_amount,
            "data_criacao": pedido.created_at
        }
        for pedido in pedidos
    ]


@app.patch("/pedidos/{pedido_id}/status")
def atualizar_status(
    pedido_id: int,
    dados: AtualizarStatusEntrada,
    db: Session = Depends(get_db),
    usuario: User = Depends(
        verificar_perfil("COZINHA", "ATENDENTE", "GERENTE")
    )
):
    pedido = buscar_pedido_autorizado(db, pedido_id, usuario)

    try:
        novo_status = StatusPedido(dados.status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Status inválido.")

    if novo_status.value not in PERMISSAO_STATUS[usuario.role]:
        raise HTTPException(
            status_code=403,
            detail="Perfil sem permissão para definir este status."
        )

    if novo_status.value not in TRANSICOES[pedido.status]:
        raise HTTPException(
            status_code=400,
            detail="Transição de status não permitida."
        )

    pedido.status = novo_status.value
    db.commit()
    db.refresh(pedido)

    return {
        "id": pedido.id,
        "status": pedido.status,
        "mensagem": "Status atualizado com sucesso."
    }


@app.patch("/pedidos/{pedido_id}/cancelar")
def cancelar_pedido(
    pedido_id: int,
    dados: CancelarPedidoEntrada,
    db: Session = Depends(get_db),
    usuario: User = Depends(
        verificar_perfil("CLIENTE", "ATENDENTE", "GERENTE")
    )
):
    pedido = buscar_pedido_autorizado(db, pedido_id, usuario)

    if not dados.motivo.strip():
        raise HTTPException(
            status_code=400,
            detail="Informe o motivo do cancelamento."
        )

    if pedido.status not in [
        StatusPedido.AGUARDANDO_PAGAMENTO.value,
        StatusPedido.PAGO.value
    ]:
        raise HTTPException(
            status_code=400,
            detail="Este pedido não pode ser cancelado."
        )

    try:
        itens = db.query(OrderItem).filter(
            OrderItem.order_id == pedido.id
        ).all()

        for item in itens:
            relacoes = db.query(ProductIngredient).filter(
                ProductIngredient.product_id == item.product_id
            ).all()

            for relacao in relacoes:
                quantidade = (
                    Decimal(str(relacao.quantity))
                    * Decimal(str(item.quantity))
                )

                estoque = db.query(Stock).filter(
                    Stock.unit_id == pedido.unit_id,
                    Stock.ingredient_id == relacao.ingredient_id
                ).first()

                if estoque:
                    estoque.quantity += quantidade

        pedido.status = StatusPedido.CANCELADO.value
        pedido.cancellation_reason = dados.motivo.strip()

        db.commit()
        db.refresh(pedido)

        return {
            "id": pedido.id,
            "status": pedido.status,
            "motivo": pedido.cancellation_reason,
            "mensagem": "Pedido cancelado com sucesso."
        }

    except Exception:
        db.rollback()
        raise


@app.post("/pedidos/{pedido_id}/pagamento")
def realizar_pagamento(
    pedido_id: int,
    dados: PagamentoEntrada,
    db: Session = Depends(get_db),
    usuario: User = Depends(
        verificar_perfil("CLIENTE", "ATENDENTE", "GERENTE")
    )
):
    # Garante 404 se o pedido não existe e 403 se está fora do escopo
    buscar_pedido_autorizado(db, pedido_id, usuario)

    try:
        pagamento = process_payment(
            db=db,
            pedido_id=pedido_id,
            tipo=dados.tipo,
            aprovado=dados.aprovado,
            falha_gateway=dados.falha_gateway
        )

        if pagamento.status == "APROVADO":
            mensagem = "Pagamento aprovado com sucesso."
        elif pagamento.status == "PENDENTE":
            mensagem = (
                "Gateway de pagamento indisponível. "
                "Pagamento pendente, tente novamente."
            )
        else:
            mensagem = "Pagamento recusado."

        return {
            "id": pagamento.id,
            "pedido_id": pagamento.pedido_id,
            "valor": pagamento.valor,
            "tipo": pagamento.tipo,
            "status": pagamento.status,
            "mensagem": mensagem
        }

    except NaoEncontrado as erro:
        raise HTTPException(status_code=404, detail=str(erro))
    except (EstoqueInsuficiente, ProdutoIndisponivel) as erro:
        raise HTTPException(status_code=409, detail=str(erro))
    except DomainError as erro:
        raise HTTPException(status_code=422, detail=str(erro))
