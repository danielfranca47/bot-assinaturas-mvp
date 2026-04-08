# Uso: python setup_webhook.py
# Registra a URL do webhook na EFI Bank para a chave Pix configurada.
# Rodar sempre que WEBHOOK_BASE_URL mudar (novo deploy no Railway, novo túnel ngrok etc.).

from efipay import EfiPay
from config import EFI_CLIENT_ID, EFI_CLIENT_SECRET, EFI_CERT_PATH, EFI_SANDBOX, EFI_PIX_KEY, WEBHOOK_BASE_URL

efi = EfiPay({
    "client_id": EFI_CLIENT_ID,
    "client_secret": EFI_CLIENT_SECRET,
    "sandbox": EFI_SANDBOX,
    "certificate": EFI_CERT_PATH,
})

webhook_url = f"{WEBHOOK_BASE_URL}/webhook/efi"
body = {"webhookUrl": webhook_url}
headers = {"x-skip-mtls-checking": "true"}

print(f"Registrando webhook: {webhook_url}")
response = efi.pix_config_webhook(params={"chave": EFI_PIX_KEY}, body=body, headers=headers)
print("Webhook registrado:", response)

# Confirma o registro
detail = efi.pix_detail_webhook(params={"chave": EFI_PIX_KEY})
print("Webhook ativo:", detail)
