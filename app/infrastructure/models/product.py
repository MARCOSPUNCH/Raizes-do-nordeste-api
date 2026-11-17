from sqlalchemy import Column, Integer, String, Boolean, Text

from app.infrastructure.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    active = Column(Boolean, default=True, nullable=False)
