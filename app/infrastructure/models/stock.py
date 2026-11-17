from sqlalchemy import (
    Column, Integer, Numeric, ForeignKey,
    UniqueConstraint, CheckConstraint
)

from app.infrastructure.database import Base


class Stock(Base):
    __tablename__ = "stocks"

    __table_args__ = (
        CheckConstraint(
            "(product_id IS NOT NULL AND ingredient_id IS NULL) OR "
            "(product_id IS NULL AND ingredient_id IS NOT NULL)",
            name="ck_stock_item"
        ),
        UniqueConstraint("unit_id", "product_id"),
        UniqueConstraint("unit_id", "ingredient_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"))
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"))
    quantity = Column(Numeric(10, 3), default=0, nullable=False)