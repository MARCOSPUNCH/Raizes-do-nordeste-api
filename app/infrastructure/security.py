from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.infrastructure.database import get_db
from app.infrastructure.models.user import User


SECRET_KEY = "raizes_nordeste_chave_secreta_2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

oauth2_scheme = HTTPBearer(auto_error=False)


def verificar_senha(senha, senha_hash):
    return pwd_context.verify(senha, senha_hash)


def gerar_hash_senha(senha):
    return pwd_context.hash(senha)


def criar_token(dados):
    conteudo = dados.copy()

    expiracao = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    conteudo.update({"exp": expiracao})

    return jwt.encode(
        conteudo,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


def verificar_token(token):
    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM]
    )


def obter_usuario_atual(
    token: HTTPAuthorizationCredentials | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    if token is None:
        raise HTTPException(
            status_code=401,
            detail="Não autenticado.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    erro = HTTPException(
        status_code=401,
        detail="Token inválido ou expirado.",
        headers={"WWW-Authenticate": "Bearer"}
    )

    try:
        dados = verificar_token(token.credentials)
        usuario_id = int(dados.get("sub"))

    except Exception:
        raise erro

    usuario = db.query(User).filter(
        User.id == usuario_id,
        User.active == True
    ).first()

    if usuario is None:
        raise erro

    return usuario


def verificar_perfil(*perfis_permitidos):
    def verificar(
        usuario: User = Depends(obter_usuario_atual)
    ):
        if usuario.role not in perfis_permitidos:
            raise HTTPException(
                status_code=403,
                detail="Usuário sem permissão para esta operação."
            )

        return usuario

    return verificar
