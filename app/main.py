from fastapi import FastAPI

from app.infrastructure.database import Base, engine
import app.infrastructure.models


Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="Rede Raízes do Nordeste API",
    description="API para gestão de pedidos, produtos e estoque.",
    version="1.0.0"
)


@app.get("/")
def home():
    return {"mensagem": "API Rede Raízes do Nordeste funcionando"}