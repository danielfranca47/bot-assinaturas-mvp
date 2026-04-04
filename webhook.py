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
