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
ADMIN_TELEGRAM_ID     = int(os.getenv("ADMIN_TELEGRAM_ID", "6970277863"))
