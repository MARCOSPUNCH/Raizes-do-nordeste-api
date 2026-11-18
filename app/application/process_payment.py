from decimal import Decimal

from sqlalchemy.orm import Session

from app.infrastructure.models.payment import Payment
from app.infrastructure.models.order import Order
from app.infrastructure.models.order_item import OrderItem
from app.infrastructure.models.product_ingredient import ProductIngredient
from app.infrastructure.models.stock import Stock
from app.domain.enums import StatusPedido, StatusPagamento
from app.domain.exceptions import DomainError, NaoEncontrado


def process_payment(
    db: Session,
    pedido_id: int,
    tipo: str,
    aprovado: bool,
    falha_gateway: bool = False
):
    try:
        pedido = db.query(Order).filter(
            Order.id == pedido_id
        ).first()

        if pedido is None:
            raise NaoEncontrado("Pedido não encontrado.")

        if pedido.status != StatusPedido.AGUARDANDO_PAGAMENTO.value:
            raise DomainError("Pedido não está aguardando pagamento.")

        # Reaproveita um pagamento PENDENTE anterior (falha do gateway),
        # evitando duas cobranças para o mesmo pedido (RNF03).
        pagamento = db.query(Payment).filter(
            Payment.pedido_id == pedido.id,
            Payment.status == StatusPagamento.PENDENTE.value
        ).first()

        if pagamento is None:
            pagamento = Payment(
                pedido_id=pedido.id,
                valor=pedido.total_amount,
                tipo=tipo,
                status=StatusPagamento.PENDENTE.value
            )
            db.add(pagamento)

        pagamento.tipo = tipo

        # Gateway fora do ar: preserva o pedido e a reserva de estoque,
        # mantém o pagamento PENDENTE e não cobra o cliente.
        if falha_gateway:
            db.commit()
            db.refresh(pagamento)
            return pagamento

        if aprovado:
            pagamento.status = StatusPagamento.APROVADO.value
            pedido.status = StatusPedido.PAGO.value
        else:
            pagamento.status = StatusPagamento.RECUSADO.value

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

        db.commit()
        db.refresh(pagamento)

        return pagamento

    except Exception:
        db.rollback()
        raise
