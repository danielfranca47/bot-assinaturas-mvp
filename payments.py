import mercadopago
from datetime import datetime, timedelta, timezone

from config import MP_ACCESS_TOKEN, WEBHOOK_BASE_URL

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

def create_pix_payment(
    telegram_user_id: int,
    amount_cents: int,
    plan: str,
    key_type: str = "copy_paste",
) -> tuple[str, str]:
    """
    Cria cobrança Pix no Mercado Pago.
    key_type: "copy_paste" ou "random"
    Retorna (pix_code, mp_payment_id).
    Para "random", retorna a chave aleatória (ticket_url) em vez do código EMV.
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
        "external_reference": str(telegram_user_id),
    }

    is_public_url = WEBHOOK_BASE_URL.startswith("https://")
    if is_public_url:
        payment_data["notification_url"] = f"{WEBHOOK_BASE_URL}/webhook/mercadopago"

    result = sdk.payment().create(payment_data)
    response = result["response"]

    if result["status"] not in (200, 201):
        raise RuntimeError(f"Erro Mercado Pago: {response}")

    transaction_data = response["point_of_interaction"]["transaction_data"]
    mp_payment_id = str(response["id"])

    if key_type == "random":
        # ticket_url é o link de pagamento do MP — não contém dados pessoais visíveis
        pix_code = transaction_data["ticket_url"]
    else:
        pix_code = transaction_data["qr_code"]

    return pix_code, mp_payment_id
