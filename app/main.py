from decimal import Decimal

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.infrastructure.database import Base, engine, get_db
import app.infrastructure.models

from app.application.create_order import create_order
from app.application.process_payment import process_payment
from app.domain.entities import ItemPedido
from app.domain.enums import StatusPedido
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


app = FastAPI(
    title="Rede Raízes do Nordeste API",
    description="API para gestão de pedidos, produtos e estoque.",
    version="1.0.0"
)


class ItemPedidoEntrada(BaseModel):
    id_produto: int
    quantidade: int
    preco_unitario: Decimal


class PedidoEntrada(BaseModel):
    id_unidade: int
    canal_pedido: str
    chave_idempotencia: str
    itens: list[ItemPedidoEntrada]
    id_usuario: int | None = None
    id_atendente: int | None = None


class AtualizarStatusEntrada(BaseModel):
    status: str


class CancelarPedidoEntrada(BaseModel):
    motivo: str


class PagamentoEntrada(BaseModel):
    tipo: str
    aprovado: bool


class LoginEntrada(BaseModel):
    email: str
    senha: str


@app.get("/")
def home():
    return {"mensagem": "API Rede Raízes do Nordeste funcionando"}


@app.post("/login")
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


@app.post("/pedidos")
def cadastrar_pedido(
    dados: PedidoEntrada,
    db: Session = Depends(get_db),
    usuario: User = Depends(verificar_perfil("GERENTE"))
):
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
            canal_pedido=dados.canal_pedido,
            chave_idempotencia=dados.chave_idempotencia,
            itens=itens,
            id_usuario=dados.id_usuario,
            id_atendente=dados.id_atendente
        )

        return {
            "id": pedido.id,
            "unidade": pedido.unit_id,
            "canal": pedido.order_channel,
            "status": pedido.status,
            "valor_total": pedido.total_amount,
            "mensagem": "Pedido cadastrado com sucesso."
        }

    except DomainError as erro:
        raise HTTPException(status_code=400, detail=str(erro))


@app.get("/pedidos")
def listar_pedidos(
    db: Session = Depends(get_db),
    usuario: User = Depends(verificar_perfil("GERENTE"))
):
    pedidos = db.query(Order).order_by(Order.id.desc()).all()

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
    usuario: User = Depends(verificar_perfil("GERENTE"))
):
    pedido = db.query(Order).filter(Order.id == pedido_id).first()

    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")

    try:
        novo_status = StatusPedido(dados.status)

        transicoes = {
            "AGUARDANDO_PAGAMENTO": [],
            "PAGO": ["EM_PREPARO"],
            "EM_PREPARO": ["PRONTO"],
            "PRONTO": ["RETIRADO"],
            "RETIRADO": [],
            "CANCELADO": []
        }

        if novo_status.value not in transicoes[pedido.status]:
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

    except ValueError:
        raise HTTPException(status_code=400, detail="Status inválido.")


@app.patch("/pedidos/{pedido_id}/cancelar")
def cancelar_pedido(
    pedido_id: int,
    dados: CancelarPedidoEntrada,
    db: Session = Depends(get_db),
    usuario: User = Depends(verificar_perfil("GERENTE"))
):
    pedido = db.query(Order).filter(Order.id == pedido_id).first()

    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")

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
    usuario: User = Depends(verificar_perfil("GERENTE"))
):
    try:
        pagamento = process_payment(
            db=db,
            pedido_id=pedido_id,
            tipo=dados.tipo,
            aprovado=dados.aprovado
        )

        if pagamento.status == "APROVADO":
            mensagem = "Pagamento aprovado com sucesso."
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
