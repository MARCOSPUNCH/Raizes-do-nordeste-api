
from sqlalchemy import (
    Column,
    Integer,
    Boolean,
    ForeignKey,
    Numeric,
    UniqueConstraint
)

from app.infrastructure.database import Base


class MenuItem(Base):
    __tablename__ = "menu_items"

    __table_args__ = (
        UniqueConstraint(
            "unit_id",
            "product_id",
            name="uq_unit_product"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    available = Column(Boolean, default=True, nullable=False)
