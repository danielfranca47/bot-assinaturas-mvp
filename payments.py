from efipay import EfiPay

from config import EFI_CLIENT_ID, EFI_CLIENT_SECRET, EFI_CERT_PATH, EFI_SANDBOX, EFI_PIX_KEY

_efi_options = {
    "client_id": EFI_CLIENT_ID,
    "client_secret": EFI_CLIENT_SECRET,
    "sandbox": EFI_SANDBOX,
    "certificate": EFI_CERT_PATH,
}


def create_pix_payment(
    telegram_user_id: int,
    amount_cents: int,
    plan: str,
) -> tuple[str, str]:
    """
    Cria cobrança Pix imediata no EFI Bank.
    Retorna (pix_copia_cola, txid).
    """
    efi = EfiPay(_efi_options)

    amount_reais = f"{amount_cents / 100:.2f}"
    plan_label = "mensal" if plan == "monthly" else "anual"

    body = {
        "calendario": {"expiracao": 1800},
        "valor": {"original": amount_reais},
        "chave": EFI_PIX_KEY,
        "solicitacaoPagador": f"Acesso {plan_label} — Canal [Nome]",
        "infoAdicionais": [
            {"nome": "telegram_user_id", "valor": str(telegram_user_id)}
        ],
    }

    try:
        charge_response = efi.pix_create_immediate_charge(body=body)
    except Exception as e:
        raise RuntimeError(f"Erro ao criar cobrança EFI: {e}") from e

    txid = charge_response.get("txid")
    loc_id = charge_response.get("loc", {}).get("id")

    if not txid or not loc_id:
        raise RuntimeError(f"Resposta inesperada da EFI: {charge_response}")

    try:
        qrcode_response = efi.pix_generate_qrcode(params={"id": loc_id})
    except Exception as e:
        raise RuntimeError(f"Erro ao gerar QR Code EFI: {e}") from e

    pix_copia_cola = qrcode_response.get("qrcode")

    if not pix_copia_cola:
        raise RuntimeError(f"QR Code não retornado pela EFI: {qrcode_response}")

    return pix_copia_cola, txid
