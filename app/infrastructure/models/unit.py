
from sqlalchemy import Column, Integer, String, Boolean

from app.infrastructure.database import Base


class Unit(Base):
    __tablename__ = "units"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    city = Column(String(100), nullable=False)
    state = Column(String(2), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
