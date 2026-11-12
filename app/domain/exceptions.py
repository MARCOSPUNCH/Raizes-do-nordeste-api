
class DomainError(Exception):
    """Exceção base para erros das regras de negócio."""


class ValorInvalido(DomainError):
    """Representa dados inválidos (HTTP 422)."""


class EstoqueInsuficiente(DomainError):
    """Representa indisponibilidade de estoque (HTTP 409)."""


class TransicaoInvalida(DomainError):
    """Representa uma mudança de estado não permitida (HTTP 409)."""


class ProdutoIndisponivel(DomainError):
    """Representa produto indisponível (HTTP 409)."""


class NaoEncontrado(DomainError):
    """Representa recurso não encontrado (HTTP 404)."""


class SemPermissao(DomainError):
    """Representa operação sem autorização (HTTP 403)."""
