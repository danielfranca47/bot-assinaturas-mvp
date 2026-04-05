# Instruções para Claude Code

---

## Sobre o Projeto

**autodigital-pay** é um bot de assinaturas para Telegram voltado a criadores de conteúdo. O MVP permite que membros adquiram acesso a canais privados via pagamento Pix (Mercado Pago), com liberação automática do link de convite após confirmação do pagamento.

O projeto atual (`bot-assinaturas-mvp/`) é um **protótipo funcional de apresentação comercial** — não o produto final. O objetivo é demonstrar o fluxo completo de ponta a ponta para fechar contratos com clientes (criadoras de conteúdo).

---

## Stack

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.11+ |
| Bot Telegram | python-telegram-bot 20.7 |
| Pagamentos | Mercado Pago SDK Python 2.2.2 |
| API/Webhook | FastAPI + Uvicorn |
| Banco de dados | SQLite (nativo `sqlite3`, sem ORM) |
| Deploy | Railway (HTTPS automático) |

---

## Estrutura do projeto

```
bot-assinaturas-mvp/
├── main.py          # entrypoint — inicia bot (polling) + FastAPI juntos via asyncio
├── bot.py           # handlers do Telegram: /assinar, escolha de plano
├── payments.py      # cria cobrança Pix via Mercado Pago SDK
├── webhook.py       # endpoint POST /webhook/mercadopago — confirma pagamento
├── database.py      # SQLite — tabela payments (sem SQLAlchemy)
├── messages.py      # todos os textos do bot (editável sem tocar no código)
├── config.py        # lê variáveis do .env, falha com mensagem clara se faltarem
├── .env             # segredos reais — NUNCA commitar
├── .env.example     # template de variáveis obrigatórias
├── requirements.txt
└── Procfile         # web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

---

## Variáveis de ambiente

Todas as variáveis ficam no `.env` (nunca commitar). O `config.py` levanta `EnvironmentError` imediatamente se alguma obrigatória estiver ausente.

```env
TELEGRAM_BOT_TOKEN=         # token do @BotFather
TELEGRAM_CHANNEL_ID=        # ID do canal privado (ex: -1001234567890)
TELEGRAM_CHANNEL_LINK=      # link fixo de convite do canal
MP_ACCESS_TOKEN=            # TEST-... em dev, APP_USR-... em produção
PRICE_MONTHLY_CENTS=2990    # R$ 29,90
PRICE_YEARLY_CENTS=29900    # R$ 299,00
WEBHOOK_BASE_URL=           # URL pública (Railway em prod, ngrok em dev)
```

---

## Banco de dados

Tabela única `payments` em `payments.db`:

```sql
CREATE TABLE IF NOT EXISTS payments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id BIGINT NOT NULL,
    username         TEXT,
    plan             TEXT NOT NULL,          -- 'monthly' ou 'yearly'
    amount_cents     INTEGER NOT NULL,
    mp_payment_id    TEXT UNIQUE,            -- ID do pagamento no Mercado Pago
    status           TEXT DEFAULT 'pending', -- 'pending', 'paid', 'expired'
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    paid_at          TIMESTAMP
);
```

Funções expostas por `database.py`: `init_db`, `insert_pending`, `update_mp_payment_id`, `mark_as_paid`.

---

## Fluxo de negócio

1. Membro envia `/assinar` → bot exibe botões inline Mensal / Anual
2. Membro escolhe plano → bot registra `pending` no banco, gera cobrança Pix, envia copia-e-cola
3. Mercado Pago dispara `POST /webhook/mercadopago` após pagamento
4. Webhook consulta status real na API do MP (nunca confiar só no payload), atualiza banco para `paid`, envia link do canal ao membro

**Campo-chave:** `external_reference` na cobrança MP = `telegram_user_id`. É como o webhook identifica o membro sem tabelas complexas.

---

## Mensagens

Todos os textos ficam em `messages.py` no dicionário `MESSAGES`. Nenhum texto fixo em outros arquivos. Isso é intencional — o cliente pode editar os textos sem precisar mexer no código.

---

## Escopo do MVP (o que NÃO implementar agora)

- Renovação automática de assinaturas
- Remoção automática de inadimplentes
- Scheduler de lembretes de vencimento
- Período de graça
- Split de pagamento
- Cancelamento de assinatura
- Links de convite rotativos por membro (no MVP o link é fixo via env)
- CPF do membro (o campo `payer` usa apenas email padrão fixo — CPF não é necessário)

---

## Decisões técnicas importantes

- **Bot + FastAPI no mesmo processo** via `asyncio`: `tg_app.start()` inicia o dispatcher; `asyncio.create_task(tg_app.updater.start_polling())` inicia o polling junto ao lifespan do FastAPI.
- **SQLite sem ORM**: deliberado para simplicidade no MVP. Não introduzir SQLAlchemy.
- **Pix copia-e-cola apenas**: QR Code não faz sentido em contexto mobile/Telegram. Usar sempre o campo `qr_code` (texto) da resposta do MP.
- **Webhook valida status no MP**: nunca assumir `approved` só pelo payload recebido. Sempre chamar `sdk.payment().get(payment_id)` para confirmar.
- **Campo `payer`**: o Mercado Pago aceita apenas email no objeto `payer` para Pix — CPF não é necessário. Usar email fixo `autodigital157@gmail.com`.
- **`MP_ACCESS_TOKEN`**: usar `TEST-...` em desenvolvimento/demo e `APP_USR-...` para produção real com dinheiro.

---

## Desenvolvimento local

```bash
cd bot-assinaturas-mvp
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # preencher com valores reais/teste

# Para testar webhook localmente:
ngrok http 8000        # copiar URL HTTPS e colocar em WEBHOOK_BASE_URL no .env

python main.py         # inicia bot + servidor na porta 8000
```

---

## Deploy (Railway)

```bash
npm install -g @railway/cli
railway login
railway init && railway up
# Configurar variáveis em: Railway → Variables
# URL pública em: Railway → Settings → Domains → setar como WEBHOOK_BASE_URL
```

---

## Commits no GitHub

Após cada tarefa concluída com alterações no código, **sempre** realizar um commit no GitHub seguindo estes passos:

1. Verificar os arquivos alterados com `git status`
2. Adicionar os arquivos relevantes com `git add <arquivos>`
3. Criar o commit com uma mensagem descritiva do que foi feito
4. Fazer push para o repositório remoto com `git push`

### Formato da mensagem de commit

```
<tipo>: <descrição curta do que foi feito>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

**Tipos:**
- `feat` — nova funcionalidade
- `fix` — correção de bug
- `refactor` — refatoração sem mudança de comportamento
- `docs` — alterações em documentação
- `chore` — tarefas de manutenção

### Regra

Nenhuma tarefa é considerada concluída sem o commit correspondente no GitHub.
