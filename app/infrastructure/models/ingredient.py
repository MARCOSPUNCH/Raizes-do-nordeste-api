from sqlalchemy import Column, Integer, String, Boolean
from app.infrastructure.database import Base


class Ingredient(Base):
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    unit_of_measure = Column(String(20), nullable=False)
    active = Column(Boolean, default=True, nullable=False)