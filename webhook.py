from efipay import EfiPay
from fastapi import APIRouter, Request

from config import (
    EFI_CLIENT_ID, EFI_CLIENT_SECRET, EFI_CERT_PATH, EFI_SANDBOX,
    TELEGRAM_CHANNEL_LINK, ADMIN_TELEGRAM_ID,
)
from database import mark_as_paid
from messages import MESSAGES

router = APIRouter()

_efi_options = {
    "client_id": EFI_CLIENT_ID,
    "client_secret": EFI_CLIENT_SECRET,
    "sandbox": EFI_SANDBOX,
    "certificate": EFI_CERT_PATH,
}

# Referência ao bot preenchida em main.py após inicialização
_bot = None


def set_bot(bot):
    global _bot
    _bot = bot


@router.post("/webhook/efi")
async def efi_webhook(request: Request):
    data = await request.json()

    if "pix" not in data:
        return {"status": "ignored"}

    for pix_item in data["pix"]:
        txid = pix_item.get("txid")
        if not txid:
            continue

        # Verificação opcional via API EFI — confirma que status é CONCLUIDA
        try:
            efi = EfiPay(_efi_options)
            charge = efi.pix_detail_charge(params={"txid": txid})
            if charge.get("status") != "CONCLUIDA":
                continue
        except Exception:
            # Em caso de falha na verificação, processa mesmo assim (pagamento já recebido)
            pass

        sale = mark_as_paid(txid)
        if sale is None:
            continue  # já processado

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
                f"TxID EFI: {txid}"
            ),
        )

    return {"status": "ok"}
