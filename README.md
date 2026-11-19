# Rede Raízes do Nordeste

## Sobre o projeto

Projeto desenvolvido no curso de Análise e Desenvolvimento de Sistemas da UNINTER. É uma API de back-end para o gerenciamento de uma rede de restaurantes de comida regional nordestina, com foco no fluxo **Pedido → Pagamento simulado → Atualização de status**.

## Tecnologias utilizadas

- Python 3.12 ou superior
- FastAPI
- SQLite
- SQLAlchemy
- JWT (autenticação) e bcrypt (hash de senha)

## Funcionalidades

- Autenticação por JWT, com perfis CLIENTE, ATENDENTE, COZINHA, GERENTE e MATRIZ.
- Criação, listagem, cancelamento e atualização de status de pedidos.
- Consulta de pedidos por canal (`canal_pedido`) e por status, com paginação.
- Pagamento simulado (aprovado, recusado e falha do gateway).
- Controle de estoque em versão básica (reserva de insumos por ficha técnica).
- Erros padronizados em JSON.

## Requisitos

- Python 3.12 ou superior
- Git

## Como executar (Windows PowerShell)

1. Clonar o repositório e entrar na pasta:

   ```
   git clone [link do repositório]
   cd Raizes-do-nordesteApi
   ```

2. Criar e ativar o ambiente virtual:

   ```
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   Se der erro de execução de scripts, rode uma vez: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

3. Instalar as dependências:

   ```
   pip install -r requirements.txt
   ```

4. Iniciar a API (na raiz do projeto, com o ambiente ativo):

   ```
   uvicorn app.main:app --reload
   ```

O banco SQLite (`raizes.db`) é criado automaticamente na primeira execução.
Sempre que abrir um terminal novo, ative o ambiente (passo 2) antes de iniciar a API.

## Documentação

Com a API rodando, a documentação interativa (Swagger) fica em:

- Swagger:(http://127.0.0.1:8000/docs)
- OpenAPI: http://127.0.0.1:8000/openapi.json

## Usuários de teste (fictícios)

| Perfil | E-mail | Senha |
|---|---|---|
| GERENTE | kyo@raizes.com | [Raizes@123] |
| ATENDENTE | mary@raizes.com | [Raizes@123] |
| COZINHA | shermie@raizes.com | [Raizes@123] |
| CLIENTE | mai@raizes.com | [Raizes@123] |
| MATRIZ | rugal@raizes.com | [Rugal@2026#Raizes] |

## Testes

Importar a coleção `Raizes_do_Nordeste.postman_collection.json` no Postman.
Ordem sugerida: Auth (fazer login e guardar o token) → Pedidos → Pagamento → Erros.

## Evidências

- Repositório: [link do repositório]
- Swagger local: http://127.0.0.1:8000/docs
- Coleção Postman: `Raizes_do_Nordeste.postman_collection.json` (na raiz do repositório)