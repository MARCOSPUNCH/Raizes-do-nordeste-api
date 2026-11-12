
from decimal import Decimal

from app.domain.enums import CanalPedido, StatusPedido, StatusPagamento
from app.domain.exceptions import (
    ValorInvalido,
    EstoqueInsuficiente,
    TransicaoInvalida,
)

TRANSICOES = {
    StatusPedido.AGUARDANDO_PAGAMENTO: [
        StatusPedido.PAGO, StatusPedido.CANCELADO
    ],
    StatusPedido.PAGO: [
        StatusPedido.EM_PREPARO, StatusPedido.CANCELADO
    ],
    StatusPedido.EM_PREPARO: [StatusPedido.PRONTO],
    StatusPedido.PRONTO: [StatusPedido.RETIRADO],
    StatusPedido.RETIRADO: [],
    StatusPedido.CANCELADO: [],
}


class ItemPedido:
    def __init__(self, id_produto, quantidade, preco_unitario):
        self.preco_unitario = Decimal(str(preco_unitario))

        if quantidade <= 0 or self.preco_unitario <= 0:
            raise ValorInvalido("Quantidade e preço devem ser positivos.")

        self.id_produto = id_produto
        self.quantidade = quantidade

    def subtotal(self):
        return self.preco_unitario * self.quantidade


class Pedido:
    def __init__(self, id_unidade, canal_pedido, chave_idempotencia,
                 itens, id_usuario=None, id_atendente=None):

        try:
            self.canal_pedido = CanalPedido(canal_pedido)
        except (ValueError, TypeError):
            raise ValorInvalido("Canal de pedido inválido.")

        if not chave_idempotencia or not itens:
            raise ValorInvalido("Chave e itens são obrigatórios.")

        if (self.canal_pedido == CanalPedido.BALCAO) != (id_atendente is not None):
            raise ValorInvalido("Atendente obrigatório somente no balcão.")

        self.id_unidade = id_unidade
        self.chave_idempotencia = chave_idempotencia
        self.itens = itens
        self.id_usuario = id_usuario
        self.id_atendente = id_atendente
        self.status = StatusPedido.AGUARDANDO_PAGAMENTO
        self.valor_total = sum(
            (item.subtotal() for item in itens), Decimal("0.00")
        )

    def mudar_status(self, novo_status):
        try:
            novo_status = StatusPedido(novo_status)
        except (ValueError, TypeError):
            raise TransicaoInvalida("Status inválido.")

        if novo_status not in TRANSICOES[self.status]:
            raise TransicaoInvalida("Transição de status não permitida.")

        self.status = novo_status

    def cancelar(self, motivo):
        if not motivo or not motivo.strip():
            raise ValorInvalido("Motivo do cancelamento obrigatório.")

        self.mudar_status(StatusPedido.CANCELADO)


class Estoque:
    def __init__(self, id_unidade, id_insumo, quantidade_atual):
        self.quantidade_atual = Decimal(str(quantidade_atual))

        if self.quantidade_atual < 0:
            raise ValorInvalido("Estoque não pode ser negativo.")

        self.id_unidade = id_unidade
        self.id_insumo = id_insumo
        self.quantidade_reservada = Decimal("0")

    def disponivel(self):
        return self.quantidade_atual - self.quantidade_reservada

    def reservar(self, quantidade):
        quantidade = Decimal(str(quantidade))

        if quantidade <= 0:
            raise ValorInvalido("Quantidade deve ser positiva.")
        if quantidade > self.disponivel():
            raise EstoqueInsuficiente("Estoque insuficiente.")

        self.quantidade_reservada += quantidade

    def liberar(self, quantidade):
        quantidade = Decimal(str(quantidade))

        if quantidade <= 0 or quantidade > self.quantidade_reservada:
            raise ValorInvalido("Quantidade reservada inválida.")

        self.quantidade_reservada -= quantidade

    def baixar(self, quantidade):
        quantidade = Decimal(str(quantidade))

        if quantidade <= 0 or quantidade > self.quantidade_reservada:
            raise EstoqueInsuficiente("Reserva insuficiente.")

        self.quantidade_atual -= quantidade
        self.quantidade_reservada -= quantidade


class Pagamento:
    def __init__(self, id_pedido, chave_idempotencia, valor):
        self.valor = Decimal(str(valor))

        if self.valor <= 0:
            raise ValorInvalido("Valor do pagamento deve ser positivo.")

        self.id_pedido = id_pedido
        self.chave_idempotencia = chave_idempotencia
        self.status = StatusPagamento.PENDENTE
        self.id_transacao_gateway = None

    def responder(self, aprovado, id_transacao=None):
        if self.status != StatusPagamento.PENDENTE:
            raise TransicaoInvalida("Pagamento já processado.")

        if not isinstance(aprovado, bool):
            raise ValorInvalido("Resposta do pagamento inválida.")

        self.status = (
            StatusPagamento.APROVADO if aprovado
            else StatusPagamento.NEGADO
        )
        self.id_transacao_gateway = id_transacao


def calcular_pontos(pedido, tem_consentimento):
    if not tem_consentimento or pedido.id_usuario is None:
        return 0

    return int(pedido.valor_total)
