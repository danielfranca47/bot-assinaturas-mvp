from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

from config import TELEGRAM_BOT_TOKEN, PRICE_MONTHLY_CENTS, PRICE_YEARLY_CENTS
from database import insert_pending, update_mp_payment_id
from messages import MESSAGES
from payments import create_pix_payment


def build_application() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("assinar", cmd_assinar))
    app.add_handler(CallbackQueryHandler(on_plan_chosen, pattern="^plan:"))
    app.add_handler(CallbackQueryHandler(on_key_type_chosen, pattern="^key:"))
    return app


async def cmd_assinar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    monthly_label = MESSAGES["plano_mensal"].format(
        valor=f"{PRICE_MONTHLY_CENTS / 100:.2f}".replace(".", ",")
    )
    yearly_label = MESSAGES["plano_anual"].format(
        valor=f"{PRICE_YEARLY_CENTS / 100:.2f}".replace(".", ",")
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(monthly_label, callback_data="plan:monthly")],
        [InlineKeyboardButton(yearly_label,  callback_data="plan:yearly")],
    ])
    await update.message.reply_text(
        MESSAGES["boas_vindas"].format(nome=user.first_name),
        reply_markup=keyboard,
    )


async def on_plan_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    plan = query.data.split(":")[1]  # "monthly" ou "yearly"
    amount_cents = PRICE_MONTHLY_CENTS if plan == "monthly" else PRICE_YEARLY_CENTS

    # Armazena o plano para o próximo passo
    context.user_data["plan"] = plan
    context.user_data["amount_cents"] = amount_cents

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(MESSAGES["tipo_chave_copia_cola"], callback_data="key:copy_paste")],
        [InlineKeyboardButton(MESSAGES["tipo_chave_aleatoria"],  callback_data="key:random")],
    ])
    await query.message.reply_text(
        MESSAGES["escolha_tipo_chave"],
        reply_markup=keyboard,
    )


async def on_key_type_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    key_type = query.data.split(":")[1]  # "copy_paste" ou "random"

    plan = context.user_data.get("plan")
    amount_cents = context.user_data.get("amount_cents")

    row_id = insert_pending(user.id, user.username, plan, amount_cents)

    pix_code, mp_payment_id = create_pix_payment(user.id, amount_cents, plan, key_type)
    update_mp_payment_id(row_id, mp_payment_id)

    if key_type == "random":
        await query.message.reply_text(MESSAGES["aguardando_pagamento_aleatoria"])
        await query.message.reply_text(
            MESSAGES["pix_chave_aleatoria"].format(chave=pix_code),
            parse_mode="Markdown",
        )
    else:
        await query.message.reply_text(MESSAGES["aguardando_pagamento"])
        await query.message.reply_text(
            MESSAGES["pix_copia_cola"].format(codigo=pix_code),
            parse_mode="Markdown",
        )
