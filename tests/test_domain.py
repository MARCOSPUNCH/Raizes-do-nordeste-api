from decimal import Decimal

import pytest

from app.domain.entities import (
    Estoque,
    ItemPedido,
    Pagamento,
    Pedido,
    calcular_pontos,
)
from app.domain.enums import StatusPagamento, StatusPedido
from app.domain.exceptions import (
    EstoqueInsuficiente,
    TransicaoInvalida,
    ValorInvalido,
)


def novo_item(quantidade=2, preco="15.50"):
    return ItemPedido(10, quantidade, preco)


def novo_pedido(canal="APP", atendente=None, quantidade=2, preco="15.50"):
    return Pedido(
        id_unidade=1,
        canal_pedido=canal,
        chave_idempotencia="chave-1",
        itens=[novo_item(quantidade, preco)],
        id_usuario=1,
        id_atendente=atendente,
    )


# TESTES DE ITEM E PEDIDO

def test_total_do_pedido():
    pedido = novo_pedido()

    assert pedido.valor_total == Decimal("31.00")


@pytest.mark.parametrize("canal", ["TELEFONE", "INVALIDO"])
def test_canal_invalido(canal):
    with pytest.raises(ValorInvalido):
        novo_pedido(canal=canal)


@pytest.mark.parametrize(
    "quantidade, preco",
    [(0, "15.50"), (-2, "15.50"), (2, "-15.50")],
)
def test_item_com_valor_invalido(quantidade, preco):
    with pytest.raises(ValorInvalido):
        novo_item(quantidade, preco)


def test_pedido_sem_itens():
    with pytest.raises(ValorInvalido):
        Pedido(1, "APP", "chave-1", [])


def test_balcao_exige_atendente():
    with pytest.raises(ValorInvalido):
        novo_pedido(canal="BALCAO")


def test_balcao_com_atendente():
    pedido = novo_pedido(canal="BALCAO", atendente=5)

    assert pedido.id_atendente == 5


def test_outros_canais_nao_aceitam_atendente():
    with pytest.raises(ValorInvalido):
        novo_pedido(atendente=5)


# TESTES DE STATUS DO PEDIDO

def test_fluxo_completo_de_status():
    pedido = novo_pedido()

    pedido.mudar_status(StatusPedido.PAGO)
    pedido.mudar_status(StatusPedido.EM_PREPARO)
    pedido.mudar_status(StatusPedido.PRONTO)
    pedido.mudar_status(StatusPedido.RETIRADO)

    assert pedido.status == StatusPedido.RETIRADO


def test_nao_cancela_apos_inicio_do_preparo():
    pedido = novo_pedido()

    pedido.mudar_status(StatusPedido.PAGO)
    pedido.mudar_status(StatusPedido.EM_PREPARO)

    with pytest.raises(TransicaoInvalida):
        pedido.cancelar("Desistência")


def test_cancelamento_com_motivo():
    pedido = novo_pedido()
    pedido.cancelar("Cliente desistiu")

    assert pedido.status == StatusPedido.CANCELADO
    assert pedido.motivo_cancelamento == "Cliente desistiu"


def test_cancelamento_sem_motivo():
    with pytest.raises(ValorInvalido):
        novo_pedido().cancelar("   ")


def test_transicao_invalida():
    with pytest.raises(TransicaoInvalida):
        novo_pedido().mudar_status(StatusPedido.PRONTO)


# TESTES DE ESTOQUE

def test_estoque_insuficiente():
    estoque = Estoque(1, 10, 2)

    with pytest.raises(EstoqueInsuficiente):
        estoque.reservar(5)


def test_reserva_de_estoque():
    estoque = Estoque(1, 10, 10)
    estoque.reservar(4)

    assert estoque.quantidade_reservada == Decimal("4")
    assert estoque.disponivel() == Decimal("6")


def test_liberacao_de_estoque():
    estoque = Estoque(1, 10, 10)
    estoque.reservar(4)
    estoque.liberar(2)

    assert estoque.quantidade_reservada == Decimal("2")


def test_nao_libera_mais_do_que_reservado():
    estoque = Estoque(1, 10, 10)
    estoque.reservar(4)

    with pytest.raises(ValorInvalido):
        estoque.liberar(5)


def test_baixa_de_estoque():
    estoque = Estoque(1, 10, 10)
    estoque.reservar(4)
    estoque.baixar(4)

    assert estoque.quantidade_atual == Decimal("6")
    assert estoque.quantidade_reservada == Decimal("0")


def test_devolucao_de_estoque():
    estoque = Estoque(1, 10, 10)
    estoque.devolver(5)

    assert estoque.quantidade_atual == Decimal("15")


def test_nao_permite_estoque_negativo():
    with pytest.raises(ValorInvalido):
        Estoque(1, 10, -5)


# TESTES DE PAGAMENTO

def test_pagamento_aprovado():
    pagamento = Pagamento(1, "chave-1", "31.00")
    pagamento.responder(True, "TX-001")

    assert pagamento.status == StatusPagamento.APROVADO
    assert pagamento.id_transacao_gateway == "TX-001"


def test_pagamento_negado():
    pagamento = Pagamento(1, "chave-1", "31.00")
    pagamento.responder(False)

    assert pagamento.status == StatusPagamento.NEGADO


def test_pagamento_nao_processa_duas_vezes():
    pagamento = Pagamento(1, "chave-1", "31.00")
    pagamento.responder(True, "TX-001")

    with pytest.raises(TransicaoInvalida):
        pagamento.responder(False)


def test_pagamento_nao_aceita_valor_negativo():
    with pytest.raises(ValorInvalido):
        Pagamento(1, "chave-1", "-10.00")


# TESTES DE FIDELIDADE

def test_pontos_com_consentimento():
    assert calcular_pontos(novo_pedido(), True) == 31


def test_pontos_sem_consentimento():
    assert calcular_pontos(novo_pedido(), False) == 0


def test_pontos_sem_usuario():
    pedido = Pedido(1, "APP", "chave-1", [novo_item()])

    assert calcular_pontos(pedido, True) == 0


def test_pontos_desconsideram_fracao():
    pedido = novo_pedido(preco="15.75")

    assert calcular_pontos(pedido, True) == 31