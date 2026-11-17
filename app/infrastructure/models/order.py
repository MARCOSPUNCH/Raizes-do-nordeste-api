from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, DateTime
from sqlalchemy.sql import func

from app.infrastructure.database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    attendant_id = Column(Integer, ForeignKey("users.id"))

    order_channel = Column(String(20), nullable=False)
    status = Column(String(30), default="AGUARDANDO_PAGAMENTO", nullable=False)
    idempotency_key = Column(String(100), unique=True, nullable=False)

    total_amount = Column(Numeric(10, 2), nullable=False)
    cancellation_reason = Column(String(255))

    created_at = Column(DateTime, server_default=func.now(), nullable=False)