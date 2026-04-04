import asyncio
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from telegram.ext import Application

from bot import build_application
from database import init_db
from webhook import router as webhook_router, set_bot

tg_app: Application | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global tg_app
    init_db()
    tg_app = build_application()
    set_bot(tg_app.bot)
    await tg_app.initialize()
    await tg_app.start()
    asyncio.create_task(tg_app.updater.start_polling())
    yield
    await tg_app.updater.stop()
    await tg_app.stop()
    await tg_app.shutdown()


app = FastAPI(lifespan=lifespan)
app.include_router(webhook_router)


@app.get("/")
def health():
    return {"status": "running"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
