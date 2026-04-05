import mercadopago
from fastapi import APIRouter, Request

from config import MP_ACCESS_TOKEN, TELEGRAM_CHANNEL_LINK, ADMIN_TELEGRAM_ID
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

    sale = mark_as_paid(payment_id)
    if sale is None:
        return {"status": "already_processed"}

    await _bot.send_message(
        chat_id=sale["telegram_user_id"],
        text=MESSAGES["pagamento_confirmado"].format(link=TELEGRAM_CHANNEL_LINK),
    )

    plano_label = "Mensal" if sale["plan"] == "monthly" else "Anual"
    valor_reais = sale["amount_cents"] / 100
    username_display = f"@{sale['username']}" if sale["username"] else f"ID {sale['telegram_user_id']}"
    await _bot.send_message(
        chat_id=ADMIN_TELEGRAM_ID,
        text=(
            f"Nova venda realizada!\n\n"
            f"Usuario: {username_display}\n"
            f"Plano: {plano_label}\n"
            f"Valor: R$ {valor_reais:.2f}\n"
            f"ID MP: {payment_id}"
        ),
    )

    return {"status": "ok"}
