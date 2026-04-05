# Bot de Assinaturas — MVP para Apresentação

## Objetivo

Construir um protótipo funcional em 1 dia para apresentação comercial com cliente (criadora de conteúdo). O bot deve demonstrar o fluxo completo de ponta a ponta: membro solicita acesso → recebe Pix copia-e-cola → paga → recebe link do canal no Telegram.

Não é o produto final. É o mínimo necessário para convencer o cliente de que a solução funciona e fechar o contrato.

---

## O que o MVP faz

- Membro manda `/assinar` no bot
- Bot responde com mensagem de boas-vindas e opções de plano (mensal / anual)
- Membro escolhe o plano
- Bot gera cobrança Pix via Mercado Pago e envia Pix copia-e-cola
- Mercado Pago confirma pagamento via webhook
- Bot envia link de convite para o canal privado do Telegram
- Bot registra o pagamento no banco de dados

## O que o MVP NÃO faz (deixar para o produto final)

- Renovação automática
- Remoção de inadimplentes
- Scheduler de lembretes
- Período de graça
- Split de pagamento
- Cancelamento de assinatura
- Links rotativos (no MVP o link é fixo por simplicidade)

---

## Mensagens personalizáveis

Todas as mensagens ficam em `messages.py` e podem ser editadas sem tocar no código. Isso é um ponto de venda importante — mostrar ao cliente que os textos são configuráveis por ele.

```python
MESSAGES = {
    "boas_vindas": "Olá, {nome}! 👋\nBem-vindo ao canal da [Nome da Lead].\nEscolha seu plano de acesso:",
    "plano_mensal": "📅 Mensal — R$ {valor}",
    "plano_anual": "📆 Anual — R$ {valor} (melhor custo-benefício!)",
    "aguardando_pagamento": "🔔 Seu Pix foi gerado!\n\nCopie o código abaixo e cole no app do seu banco para pagar.\nSeu acesso será liberado automaticamente.\n\n⏳ Válido por 30 minutos.",
    "pix_copia_cola": "📋 Pix copia e cola:\n\n`{codigo}`\n\nAbra o app do banco → Pix → Pagar → Copia e cola.",
    "pagamento_confirmado": "✅ Pagamento confirmado!\n\nSeu acesso foi liberado. Clique no link abaixo para entrar no canal:\n{link}",
    "pagamento_expirado": "❌ O tempo para pagamento expirou.\nMande /assinar para gerar um novo código Pix.",
}
```

---

## Stack do MVP

- **Python 3.11+**
- **python-telegram-bot** — bot e handlers
- **mercadopago** (SDK oficial Python) — gerar cobrança Pix
- **FastAPI + Uvicorn** — receber webhook do Mercado Pago
- **SQLite** com uma tabela simples via `sqlite3` nativo (sem SQLAlchemy)
- **Railway** — deploy com HTTPS automático

---

## Estrutura de arquivos

```
bot-assinaturas-mvp/
│
├── main.py          # inicia bot + servidor FastAPI juntos
├── bot.py           # handlers do Telegram (/assinar, escolha de plano)
├── payments.py      # gera cobrança Pix via Mercado Pago
├── webhook.py       # endpoint FastAPI que recebe confirmação do MP
├── database.py      # SQLite simples — uma tabela de pagamentos
├── messages.py      # todos os textos do bot (editável sem mexer no código)
├── config.py        # lê variáveis do .env
│
├── .env             # segredos reais (nunca commitar)
├── .env.example     # template com variáveis necessárias
├── .gitignore
├── requirements.txt
└── Procfile         # web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

---

## Variáveis de ambiente

```env
# Telegram
TELEGRAM_BOT_TOKEN=         # token do @BotFather (ex: 7412589631:AAFxyz...)
TELEGRAM_CHANNEL_ID=        # ID do canal privado (ex: -1001234567890)
TELEGRAM_CHANNEL_LINK=      # link fixo de convite do canal (ex: https://t.me/+abc123)

# Mercado Pago
MP_ACCESS_TOKEN=             # token de produção (APP_USR-...) ou teste (TEST-...)

# Preços em centavos
PRICE_MONTHLY_CENTS=2990     # R$ 29,90
PRICE_YEARLY_CENTS=29900     # R$ 299,00

# App
WEBHOOK_BASE_URL=            # URL pública do Railway (ex: https://seu-app.up.railway.app)
```

---

## Tabela do banco de dados (única)

```sql
CREATE TABLE IF NOT EXISTS payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id BIGINT NOT NULL,
    username        TEXT,
    plan            TEXT NOT NULL,          -- 'monthly' ou 'yearly'
    amount_cents    INTEGER NOT NULL,
    mp_payment_id   TEXT UNIQUE,            -- ID do pagamento no Mercado Pago
    status          TEXT DEFAULT 'pending', -- 'pending', 'paid', 'expired'
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    paid_at         TIMESTAMP
);
```

---

## Fluxo técnico detalhado

### 1. Membro inicia
```
Membro → /assinar
Bot → mensagem de boas-vindas com botões inline: [Mensal R$29,90] [Anual R$299,00]
```

### 2. Membro escolhe plano
```
Membro → clica no botão
Bot → registra pending no banco com telegram_user_id + plano
Bot → chama Mercado Pago API para criar cobrança Pix
Bot → envia Pix copia-e-cola ao membro (texto copiável)
```

### 3. Membro paga
```
Mercado Pago → dispara webhook POST /webhook/mercadopago
Webhook → identifica pagamento pelo mp_payment_id
Webhook → atualiza status para 'paid' no banco
Webhook → bot envia link do canal ao membro via Telegram
```

---

## Chamada à API do Mercado Pago (Pix)

```python
import mercadopago

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

payment_data = {
    "transaction_amount": 29.90,
    "description": "Acesso mensal — Canal da [Nome]",
    "payment_method_id": "pix",
    "payer": {
        "email": "membro@email.com",  # pode ser genérico no MVP
        "first_name": "Membro",
        "last_name": "Telegram",
        "identification": {
            "type": "CPF",
            "number": "00000000000"   # CPF genérico no MVP
        }
    },
    "date_of_expiration": "2025-01-01T23:59:59.000-03:00",  # 30 min no futuro
    "notification_url": f"{WEBHOOK_BASE_URL}/webhook/mercadopago",
    "external_reference": str(telegram_user_id)  # para identificar quem pagou
}

result = sdk.payment().create(payment_data)
payment = result["response"]

# Apenas o código copia-e-cola — QR Code não faz sentido em mobile
pix_copia_cola = payment["point_of_interaction"]["transaction_data"]["qr_code"]
mp_payment_id  = payment["id"]
```

---

## Webhook do Mercado Pago

```python
@app.post("/webhook/mercadopago")
async def mercadopago_webhook(request: Request):
    data = await request.json()

    # MP envia notificação com o ID do pagamento
    if data.get("type") == "payment":
        payment_id = data["data"]["id"]

        # Consulta o pagamento na API do MP para confirmar status
        payment_info = sdk.payment().get(payment_id)
        status = payment_info["response"]["status"]

        if status == "approved":
            external_reference = payment_info["response"]["external_reference"]
            telegram_user_id = int(external_reference)

            # Atualiza banco e envia link ao membro
            mark_as_paid(telegram_user_id, payment_id)
            await bot.send_message(
                chat_id=telegram_user_id,
                text=MESSAGES["pagamento_confirmado"].format(link=TELEGRAM_CHANNEL_LINK)
            )

    return {"status": "ok"}
```

---

## Observações para implementação

1. **`external_reference`** é o campo chave — é onde guardamos o `telegram_user_id` na cobrança do Mercado Pago. Quando o webhook chega, usamos esse campo para saber qual membro pagou, sem precisar de tabelas complexas.

2. **CPF genérico no MVP** — o Mercado Pago exige CPF no campo `payer`, mas para o MVP de apresentação pode-se usar um CPF de teste genérico. No produto final o membro informa o próprio CPF.

3. **Link fixo do canal** — no MVP o link de convite é fixo (uma variável de ambiente). No produto final cada membro recebe um link único gerado e revogado individualmente.

4. **Webhook local durante desenvolvimento** — para testar o webhook localmente antes do deploy, usar o [ngrok](https://ngrok.com) para expor a porta local com HTTPS temporário. Comando: `ngrok http 8000`. Colocar a URL gerada no `.env` como `WEBHOOK_BASE_URL`.

5. **Credenciais de teste vs produção** — durante o desenvolvimento usar `TEST-...` no `MP_ACCESS_TOKEN`. Para a demo real com a lead, trocar para `APP_USR-...`. Com o token de teste os pagamentos são simulados e não movem dinheiro real.

6. **Pix exige chave cadastrada** — a conta do Mercado Pago precisa ter uma chave Pix cadastrada no app antes de gerar cobranças. Verificar isso antes de começar.

---
