from sqlalchemy import Column, Integer, String, Boolean, ForeignKey

from app.infrastructure.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)
    unit_id = Column(Integer, ForeignKey("units.id"))
    active = Column(Boolean, default=True, nullable=False)