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
        "external_reference": str(telegram_user_id),
    }

    is_public_url = WEBHOOK_BASE_URL.startswith("https://")
    if is_public_url:
        payment_data["notification_url"] = f"{WEBHOOK_BASE_URL}/webhook/mercadopago"

    result = sdk.payment().create(payment_data)
    response = result["response"]

    if result["status"] not in (200, 201):
        raise RuntimeError(f"Erro Mercado Pago: {response}")

    pix_code = response["point_of_interaction"]["transaction_data"]["qr_code"]
    mp_payment_id = str(response["id"])

    return pix_code, mp_payment_id
