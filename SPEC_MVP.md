# SPEC_MVP — Plano de Implementação: Bot de Assinaturas

Stack: Python 3.11+, python-telegram-bot, mercadopago SDK, FastAPI, SQLite, Railway.

---

## Etapa 1 — Estrutura inicial do projeto

### O que será implementado

Criação da estrutura de pastas e arquivos de configuração base do projeto.

### Arquivos criados

```
bot-assinaturas-mvp/
├── .env.example
├── .gitignore
├── requirements.txt
└── Procfile
```

**requirements.txt**
```
python-telegram-bot==20.7
mercadopago==2.2.2
fastapi==0.110.0
uvicorn==0.29.0
python-dotenv==1.0.1
httpx==0.27.0
```

**.env.example**
```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHANNEL_ID=
TELEGRAM_CHANNEL_LINK=
MP_ACCESS_TOKEN=
PRICE_MONTHLY_CENTS=2990
PRICE_YEARLY_CENTS=29900
WEBHOOK_BASE_URL=
```

**.gitignore**
```
.env
*.db
__pycache__/
*.pyc
.venv/
```

**Procfile**
```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

### Como testar

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# Deve instalar sem erros
cp .env.example .env
# Preencher .env com os valores reais antes de continuar
```

---

## Etapa 2 — config.py e database.py

### O que será implementado

- `config.py`: lê todas as variáveis do `.env` e expõe como constantes tipadas. Falha com mensagem clara se algo obrigatório estiver faltando.
- `database.py`: cria o banco SQLite `payments.db` com a tabela `payments` e expõe as funções de acesso (`insert_pending`, `mark_as_paid`, `get_payment_by_user`).

### Arquivos criados

**config.py**
```python
from dotenv import load_dotenv
import os

load_dotenv()

def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(f"Variável de ambiente obrigatória não definida: {key}")
    return value

TELEGRAM_BOT_TOKEN    = _require("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID   = int(_require("TELEGRAM_CHANNEL_ID"))
TELEGRAM_CHANNEL_LINK = _require("TELEGRAM_CHANNEL_LINK")
MP_ACCESS_TOKEN       = _require("MP_ACCESS_TOKEN")
PRICE_MONTHLY_CENTS   = int(os.getenv("PRICE_MONTHLY_CENTS", "2990"))
PRICE_YEARLY_CENTS    = int(os.getenv("PRICE_YEARLY_CENTS", "29900"))
WEBHOOK_BASE_URL      = _require("WEBHOOK_BASE_URL")
```

**database.py**
```python
import sqlite3
from datetime import datetime

DB_PATH = "payments.db"

def get_conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id BIGINT NOT NULL,
                username         TEXT,
                plan             TEXT NOT NULL,
                amount_cents     INTEGER NOT NULL,
                mp_payment_id    TEXT UNIQUE,
                status           TEXT DEFAULT 'pending',
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at          TIMESTAMP
            )
        """)
        conn.commit()

def insert_pending(telegram_user_id: int, username: str, plan: str, amount_cents: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO payments (telegram_user_id, username, plan, amount_cents) VALUES (?, ?, ?, ?)",
            (telegram_user_id, username, plan, amount_cents)
        )
        conn.commit()
        return cur.lastrowid

def update_mp_payment_id(row_id: int, mp_payment_id: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE payments SET mp_payment_id = ? WHERE id = ?",
            (mp_payment_id, row_id)
        )
        conn.commit()

def mark_as_paid(mp_payment_id: str) -> int | None:
    """Marca como pago e retorna o telegram_user_id."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE payments SET status = 'paid', paid_at = ? WHERE mp_payment_id = ? AND status = 'pending'",
            (datetime.utcnow(), mp_payment_id)
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        row = conn.execute(
            "SELECT telegram_user_id FROM payments WHERE mp_payment_id = ?",
            (mp_payment_id,)
        ).fetchone()
        return row[0] if row else None
```

### Como testar

```python
# No terminal Python
from database import init_db, insert_pending, mark_as_paid
init_db()
row_id = insert_pending(123456789, "testuser", "monthly", 2990)
print(row_id)  # deve imprimir 1
# payments.db deve aparecer no diretório
```

---

## Etapa 3 — messages.py e payments.py

### O que será implementado

- `messages.py`: dicionário central com todos os textos do bot. Nenhum texto fixo em outros arquivos.
- `payments.py`: cria cobrança Pix via Mercado Pago SDK e retorna o código copia-e-cola e o `mp_payment_id`.

### Arquivos criados

**messages.py**
```python
MESSAGES = {
    "boas_vindas": (
        "Olá, {nome}! 👋\n"
        "Bem-vindo ao canal da [Nome da Lead].\n"
        "Escolha seu plano de acesso:"
    ),
    "plano_mensal":  "📅 Mensal — R$ {valor}",
    "plano_anual":   "📆 Anual — R$ {valor} (melhor custo-benefício!)",
    "aguardando_pagamento": (
        "🔔 Seu Pix foi gerado!\n\n"
        "Copie o código abaixo e cole no app do seu banco para pagar.\n"
        "Seu acesso será liberado automaticamente.\n\n"
        "⏳ Válido por 30 minutos."
    ),
    "pix_copia_cola": (
        "📋 Pix copia e cola:\n\n"
        "`{codigo}`\n\n"
        "Abra o app do banco → Pix → Pagar → Copia e cola."
    ),
    "pagamento_confirmado": (
        "✅ Pagamento confirmado!\n\n"
        "Seu acesso foi liberado. Clique no link abaixo para entrar no canal:\n"
        "{link}"
    ),
    "pagamento_expirado": (
        "❌ O tempo para pagamento expirou.\n"
        "Mande /assinar para gerar um novo código Pix."
    ),
}
```

**payments.py**
```python
import mercadopago
from datetime import datetime, timedelta, timezone

from config import MP_ACCESS_TOKEN, WEBHOOK_BASE_URL

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

def create_pix_payment(
    telegram_user_id: int,
    amount_cents: int,
    plan: str,
) -> tuple[str, str]:
    """
    Cria cobrança Pix no Mercado Pago.
    Retorna (pix_copia_cola, mp_payment_id).
    """
    amount = amount_cents / 100
    expiration = (
        datetime.now(timezone(timedelta(hours=-3))) + timedelta(minutes=30)
    ).strftime("%Y-%m-%dT%H:%M:%S.000-03:00")

    plan_label = "mensal" if plan == "monthly" else "anual"

    payment_data = {
        "transaction_amount": amount,
        "description": f"Acesso {plan_label} — Canal da [Nome]",
        "payment_method_id": "pix",
        "payer": {
            "email": "autodigital157@gmail.com",
        },
        "date_of_expiration": expiration,
        "notification_url": f"{WEBHOOK_BASE_URL}/webhook/mercadopago",
        "external_reference": str(telegram_user_id),
    }

    result = sdk.payment().create(payment_data)
    response = result["response"]

    if result["status"] not in (200, 201):
        raise RuntimeError(f"Erro Mercado Pago: {response}")

    pix_code = response["point_of_interaction"]["transaction_data"]["qr_code"]
    mp_payment_id = str(response["id"])

    return pix_code, mp_payment_id
```

### Como testar

```bash
# Com MP_ACCESS_TOKEN de teste (TEST-...) configurado no .env:
python - <<'EOF'
from payments import create_pix_payment
code, mp_id = create_pix_payment(123456789, 2990, "monthly")
print("PIX:", code[:40], "...")
print("ID:", mp_id)
EOF
# Deve imprimir um código Pix e um ID numérico do MP
```

---

## Etapa 4 — bot.py (handlers /assinar e escolha de plano)

### O que será implementado

Handlers do Telegram:
- `/assinar` → mensagem de boas-vindas com botões inline Mensal / Anual.
- `callback_query` do botão → registra pending no banco, gera Pix, envia copia-e-cola.

### Arquivo criado

**bot.py**
```python
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

from config import TELEGRAM_BOT_TOKEN, PRICE_MONTHLY_CENTS, PRICE_YEARLY_CENTS
from database import insert_pending, update_mp_payment_id
from messages import MESSAGES
from payments import create_pix_payment

def build_application() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("assinar", cmd_assinar))
    app.add_handler(CallbackQueryHandler(on_plan_chosen, pattern="^plan:"))
    return app

async def cmd_assinar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    monthly_label = MESSAGES["plano_mensal"].format(
        valor=f"{PRICE_MONTHLY_CENTS / 100:.2f}".replace(".", ",")
    )
    yearly_label = MESSAGES["plano_anual"].format(
        valor=f"{PRICE_YEARLY_CENTS / 100:.2f}".replace(".", ",")
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(monthly_label, callback_data="plan:monthly")],
        [InlineKeyboardButton(yearly_label,  callback_data="plan:yearly")],
    ])
    await update.message.reply_text(
        MESSAGES["boas_vindas"].format(nome=user.first_name),
        reply_markup=keyboard,
    )

async def on_plan_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    plan = query.data.split(":")[1]  # "monthly" ou "yearly"
    amount_cents = PRICE_MONTHLY_CENTS if plan == "monthly" else PRICE_YEARLY_CENTS

    row_id = insert_pending(user.id, user.username, plan, amount_cents)

    pix_code, mp_payment_id = create_pix_payment(user.id, amount_cents, plan)
    update_mp_payment_id(row_id, mp_payment_id)

    await query.message.reply_text(MESSAGES["aguardando_pagamento"])
    await query.message.reply_text(
        MESSAGES["pix_copia_cola"].format(codigo=pix_code),
        parse_mode="Markdown",
    )
```

### Como testar

```bash
# Rodar o bot isoladamente (sem FastAPI):
python - <<'EOF'
from bot import build_application
app = build_application()
print("Handlers registrados:", len(app.handlers[0]))
app.run_polling()   # Ctrl+C para parar
EOF
# No Telegram: mande /assinar ao bot
# Deve aparecer a mensagem de boas-vindas com dois botões
# Ao clicar em um botão, deve receber o Pix copia-e-cola (com token TEST-)
```

---

## Etapa 5 — webhook.py (confirmação do Mercado Pago)

### O que será implementado

Endpoint FastAPI `POST /webhook/mercadopago`:
1. Recebe notificação do Mercado Pago.
2. Consulta o pagamento na API do MP para confirmar o status (nunca confiar apenas no payload).
3. Se `approved`, atualiza o banco e envia o link do canal via bot.

### Arquivo criado

**webhook.py**
```python
import mercadopago
from fastapi import APIRouter, Request

from config import MP_ACCESS_TOKEN, TELEGRAM_CHANNEL_LINK
from database import mark_as_paid
from messages import MESSAGES

router = APIRouter()
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# Referência ao bot preenchida em main.py após inicialização
_bot = None

def set_bot(bot):
    global _bot
    _bot = bot

@router.post("/webhook/mercadopago")
async def mercadopago_webhook(request: Request):
    data = await request.json()

    if data.get("type") != "payment":
        return {"status": "ignored"}

    payment_id = str(data["data"]["id"])

    # Consulta o status real na API do MP
    result = sdk.payment().get(payment_id)
    payment_info = result["response"]

    if payment_info.get("status") != "approved":
        return {"status": "not_approved"}

    telegram_user_id = mark_as_paid(payment_id)
    if telegram_user_id is None:
        return {"status": "already_processed"}

    await _bot.send_message(
        chat_id=telegram_user_id,
        text=MESSAGES["pagamento_confirmado"].format(link=TELEGRAM_CHANNEL_LINK),
    )

    return {"status": "ok"}
```

### Como testar

```bash
# Simular webhook manualmente com curl (bot e servidor rodando):
curl -X POST http://localhost:8000/webhook/mercadopago \
  -H "Content-Type: application/json" \
  -d '{"type": "payment", "data": {"id": "<mp_payment_id_real>"}}'
# Deve retornar {"status":"ok"} e enviar o link ao usuário no Telegram
```

---

## Etapa 6 — main.py (integração bot + FastAPI)

### O que será implementado

`main.py` inicializa o banco, cria a aplicação Telegram, monta o FastAPI e roda ambos no mesmo processo usando `asyncio`.

### Arquivo criado

**main.py**
```python
import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from telegram.ext import Application

from bot import build_application
from database import init_db
from webhook import router as webhook_router, set_bot

tg_app: Application | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global tg_app
    init_db()
    tg_app = build_application()
    set_bot(tg_app.bot)
    await tg_app.initialize()
    await tg_app.start()
    yield
    await tg_app.stop()
    await tg_app.shutdown()

app = FastAPI(lifespan=lifespan)
app.include_router(webhook_router)

@app.get("/")
def health():
    return {"status": "running"}

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
```

> **Atenção:** nesta configuração o bot usa **polling** embutido no `run_polling()` do python-telegram-bot.
> Para rodar bot (polling) + FastAPI (uvicorn) juntos no mesmo processo, o `tg_app.start()` inicia o dispatcher mas **não** inicia o polling automaticamente.
> Adicionar a task de polling no lifespan:

```python
# Dentro do lifespan, antes do yield:
asyncio.create_task(tg_app.updater.start_polling())
# Dentro do yield cleanup:
await tg_app.updater.stop()
```

### Como testar

```bash
python main.py
# Deve imprimir: Uvicorn running on http://0.0.0.0:8000
# GET http://localhost:8000/  → {"status":"running"}
# Bot deve responder a /assinar no Telegram
```

---

## Etapa 7 — Teste local com ngrok

### O que será implementado

Expor o servidor local via HTTPS temporário com ngrok para que o Mercado Pago consiga chamar o webhook.

### Passo a passo

```bash
# 1. Instalar ngrok (se não tiver): https://ngrok.com/download
# 2. Em um terminal, rodar o servidor:
python main.py

# 3. Em outro terminal, expor a porta 8000:
ngrok http 8000
# Copiar a URL HTTPS gerada, ex: https://a1b2c3d4.ngrok-free.app

# 4. Atualizar o .env:
WEBHOOK_BASE_URL=https://a1b2c3d4.ngrok-free.app

# 5. Reiniciar o servidor para aplicar a nova URL
python main.py
```

### Fluxo de teste completo

1. No Telegram, mandar `/assinar` ao bot.
2. Escolher um plano — receber o Pix copia-e-cola.
3. No painel do Mercado Pago (sandbox), simular aprovação do pagamento.
4. O webhook em `/webhook/mercadopago` deve ser chamado pelo MP.
5. O bot deve enviar a mensagem de pagamento confirmado com o link do canal.

### Verificação

```bash
# Logs do ngrok (http://127.0.0.1:4040) mostram as requisições recebidas do MP
# Confirmar no banco:
python - <<'EOF'
import sqlite3
conn = sqlite3.connect("payments.db")
for row in conn.execute("SELECT * FROM payments"):
    print(row)
EOF
# A linha deve ter status='paid' e paid_at preenchido
```

---

## Etapa 8 — Deploy no Railway

### O que será implementado

Deploy do projeto no Railway com variáveis de ambiente configuradas e HTTPS automático.

### Passo a passo

```bash
# 1. Criar conta em railway.app e instalar a CLI:
npm install -g @railway/cli
railway login

# 2. Na raiz do projeto:
railway init          # criar novo projeto
railway up            # fazer deploy

# 3. No painel do Railway → Variables → adicionar todas as variáveis do .env:
#    TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, TELEGRAM_CHANNEL_LINK,
#    MP_ACCESS_TOKEN, PRICE_MONTHLY_CENTS, PRICE_YEARLY_CENTS, WEBHOOK_BASE_URL

# 4. Pegar a URL pública gerada pelo Railway (Settings → Domains)
#    Ex: https://bot-assinaturas-mvp.up.railway.app

# 5. Atualizar WEBHOOK_BASE_URL no Railway com essa URL e fazer redeploy
```

### Checklist de verificação pós-deploy

- [ ] `GET https://<seu-app>.up.railway.app/` retorna `{"status":"running"}`
- [ ] Bot responde a `/assinar` no Telegram
- [ ] Após escolher plano, Pix copia-e-cola é enviado
- [ ] Webhook recebe confirmação do MP (verificar logs no Railway)
- [ ] Link do canal é enviado ao membro após pagamento aprovado
- [ ] Registro aparece com `status='paid'` na tabela `payments`

### Trocar para produção

Quando for fazer a demo real com a cliente:

```env
# Trocar no Railway:
MP_ACCESS_TOKEN=APP_USR-...   # token de produção (APP_USR-, não TEST-)
```

> Conta do Mercado Pago deve ter chave Pix cadastrada no app antes de gerar cobranças.
