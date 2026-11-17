from decimal import Decimal
from sqlalchemy.orm import Session

from app.infrastructure.models.payment import Payment
from app.infrastructure.models.order import Order
from app.infrastructure.models.order_item import OrderItem
from app.infrastructure.models.product_ingredient import ProductIngredient
from app.infrastructure.models.stock import Stock

from app.domain.enums import StatusPedido
from app.domain.exceptions import DomainError


def process_payment(
    db: Session,
    pedido_id: int,
    tipo: str,
    aprovado: bool
):
    try:
        pedido = db.query(Order).filter(
            Order.id == pedido_id
        ).first()

        if pedido is None:
            raise DomainError("Pedido não encontrado.")

        if pedido.status != StatusPedido.AGUARDANDO_PAGAMENTO.value:
            raise DomainError("Pedido não está aguardando pagamento.")

        pagamento = Payment(
            pedido_id=pedido.id,
            valor=pedido.total_amount,
            tipo=tipo,
            status="APROVADO" if aprovado else "RECUSADO"
        )

        db.add(pagamento)

        if aprovado:
            pedido.status = StatusPedido.PAGO.value

        else:
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
