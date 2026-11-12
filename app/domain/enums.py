from enum import StrEnum

class CanalPedido(StrEnum):
    APP = "APP"
    TOTEM = "TOTEM"
    BALCAO = "BALCAO"
    PICKUP = "PICKUP"
    WEB = "WEB"


class StatusPedido(StrEnum):
    AGUARDANDO_PAGAMENTO = "AGUARDANDO_PAGAMENTO"
    PAGO = "PAGO"
    EM_PREPARO = "EM_PREPARO"
    PRONTO = "PRONTO"
    RETIRADO = "RETIRADO"
    CANCELADO = "CANCELADO"


class StatusPagamento(StrEnum):
    PENDENTE = "PENDENTE"
    APROVADO = "APROVADO"
    NEGADO = "NEGADO"


class PerfilUsuario(StrEnum):
    CLIENTE = "CLIENTE"
    ATENDENTE = "ATENDENTE"
    COZINHA = "COZINHA"
    GERENTE = "GERENTE"
    MATRIZ = "MATRIZ"


class TipoMovimentoPontos(StrEnum):
    CREDITO = "CREDITO"
    ESTORNO = "ESTORNO"