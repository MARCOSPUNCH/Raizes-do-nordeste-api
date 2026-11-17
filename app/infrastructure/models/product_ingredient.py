from sqlalchemy import Column, Integer, Numeric, ForeignKey, UniqueConstraint

from app.infrastructure.database import Base


class ProductIngredient(Base):
    __tablename__ = "product_ingredients"

    __table_args__ = (
        UniqueConstraint("product_id", "ingredient_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    quantity = Column(Numeric(10, 3), nullable=False)
