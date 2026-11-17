from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime,
    ForeignKey, CheckConstraint
)
from sqlalchemy.sql import func

from app.infrastructure.database import Base


class StockMovement(Base):
    __tablename__ = "stock_movements"

    __table_args__ = (
        CheckConstraint(
            "(product_id IS NOT NULL AND ingredient_id IS NULL) OR "
            "(product_id IS NULL AND ingredient_id IS NOT NULL)",
            name="ck_stock_movement_item"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"))
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"))
    movement_type = Column(String(20), nullable=False)
    quantity = Column(Numeric(10, 3), nullable=False)
    description = Column(String(255))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)