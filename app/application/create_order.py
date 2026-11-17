from app.domain.entities import Pedido, ItemPedido
from app.domain.exceptions import (
    EstoqueInsuficiente,
    ProdutoIndisponivel,
    NaoEncontrado
)

from app.infrastructure.models.order import Order
from app.infrastructure.models.order_item import OrderItem
from app.infrastructure.models.unit import Unit
from app.infrastructure.models.product import Product
from app.infrastructure.models.menu_item import MenuItem
from app.infrastructure.models.ingredient import Ingredient
from app.infrastructure.models.product_ingredient import ProductIngredient
from app.infrastructure.models.stock import Stock


def create_order(
    db,
    id_unidade,
    canal_pedido,
    chave_idempotencia,
    itens,
    id_usuario=None,
    id_atendente=None
):
    try:
        pedido_existente = db.query(Order).filter(
        Order.idempotency_key == chave_idempotencia
        ).first()

        if pedido_existente:
            return pedido_existente
            
        unidade = db.query(Unit).filter(
            Unit.id == id_unidade,
            Unit.active == True
        ).first()

        if unidade is None:
            raise NaoEncontrado("Unidade não encontrada ou inativa.")

        itens_validados = []
        reservas = []

        for item in itens:
            produto = db.query(Product).filter(
                Product.id == item.id_produto,
                Product.active == True
            ).first()

            if produto is None:
                raise NaoEncontrado("Produto não encontrado ou inativo.")

            menu = db.query(MenuItem).filter(
                MenuItem.unit_id == id_unidade,
                MenuItem.product_id == item.id_produto,
                MenuItem.available == True
            ).first()

            if menu is None:
                raise ProdutoIndisponivel(
                    "Produto não disponível no cardápio desta unidade."
                )

            ingredientes = db.query(ProductIngredient).filter(
                ProductIngredient.product_id == item.id_produto
            ).all()

            if not ingredientes:
                raise ProdutoIndisponivel(
                    "Produto sem ingredientes cadastrados."
                )

            for relacao in ingredientes:
                ingrediente = db.query(Ingredient).filter(
                    Ingredient.id == relacao.ingredient_id,
                    Ingredient.active == True
                ).first()

                if ingrediente is None:
                    raise ProdutoIndisponivel(
                        "Ingrediente não encontrado ou inativo."
                    )

                estoque = db.query(Stock).filter(
                    Stock.unit_id == id_unidade,
                    Stock.ingredient_id == relacao.ingredient_id
                ).first()

                quantidade_necessaria = (
                    relacao.quantity * item.quantidade
                )

                if (
                    estoque is None
                    or estoque.quantity < quantidade_necessaria
                ):
                    raise EstoqueInsuficiente(
                        f"Estoque insuficiente de {ingrediente.name}."
                    )

                reservas.append((estoque, quantidade_necessaria))

            itens_validados.append(
                ItemPedido(
                    id_produto=item.id_produto,
                    quantidade=item.quantidade,
                    preco_unitario=menu.price
                )
            )

        pedido = Pedido(
            id_unidade=id_unidade,
            canal_pedido=canal_pedido,
            chave_idempotencia=chave_idempotencia,
            itens=itens_validados,
            id_usuario=id_usuario,
            id_atendente=id_atendente
        )

        pedido_db = Order(
            unit_id=pedido.id_unidade,
            user_id=pedido.id_usuario,
            attendant_id=pedido.id_atendente,
            order_channel=pedido.canal_pedido.value,
            status=pedido.status.value,
            idempotency_key=pedido.chave_idempotencia,
            total_amount=pedido.valor_total
        )

        db.add(pedido_db)
        db.flush()

        for item in pedido.itens:
            item_db = OrderItem(
                order_id=pedido_db.id,
                product_id=item.id_produto,
                quantity=item.quantidade,
                unit_price=item.preco_unitario
            )
            db.add(item_db)

        for estoque, quantidade in reservas:
            estoque.quantity -= quantidade

        db.commit()
        db.refresh(pedido_db)

        return pedido_db

    except Exception:
        db.rollback()
        raise
