import os
import json
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
scheduler = AsyncIOScheduler()


def parse_reminder(text: str) -> dict:
    now = datetime.now()
    prompt = f"""Sos un asistente que parsea recordatorios en español.
Fecha y hora actual: {now.strftime("%Y-%m-%d %H:%M")} (día: {now.strftime("%A")})
Mensaje: "{text}"
Respondé SOLO con JSON válido sin markdown ni texto extra:
{{"tarea":"descripción","datetime":"YYYY-MM-DD HH:MM","valido":true,"error":""}}
Reglas: lunes=próximo lunes, mañana=mañana, hoy=hoy. Sin hora=09:00. Fecha pasada=valido false."""

    resp = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}]
    )
    return json.loads(resp.content[0].text.strip())


async def send_reminder(bot, chat_id: int, tarea: str):
    await bot.send_message(chat_id=chat_id, text=f"🔔 Recordatorio: {tarea}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hola! Soy tu bot de recordatorios.\n\n"
        "Escribime algo como:\n"
        "el lunes a las 11 recordame comprar camiseta\n"
        "mañana a las 9 llamar al médico\n\n"
        "Usá /lista para ver tus recordatorios activos."
    )


async def lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    jobs = [j for j in scheduler.get_jobs() if str(chat_id) in j.id]
    if not jobs:
        await update.message.reply_text("No tenés recordatorios activos.")
        return
    msg = "Tus recordatorios:\n\n"
    for job in jobs:
        msg += f"• {job.args[2]} — {job.next_run_time.strftime('%d/%m %H:%M')}\n"
    await update.message.reply_text(msg)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.message.chat_id
    await update.message.reply_text("⏳ Un momento...")
    try:
        parsed = parse_reminder(text)
        if not parsed.get("valido", False):
            await update.message.reply_text(f"❌ {parsed.get('error', 'No entendí el recordatorio.')}")
            return
        reminder_dt = datetime.strptime(parsed["datetime"], "%Y-%m-%d %H:%M")
        if reminder_dt <= datetime.now():
            await update.message.reply_text("❌ Esa fecha ya pasó.")
            return
        job_id = f"{chat_id}_{parsed['datetime'].replace(' ','_').replace(':','')}".replace("-","")
        scheduler.add_job(send_reminder, "date", run_date=reminder_dt,
                         args=[context.bot, chat_id, parsed["tarea"]],
                         id=job_id, replace_existing=True)
        await update.message.reply_text(
            f"✅ Recordatorio guardado\n📌 {parsed['tarea']}\n📅 {reminder_dt.strftime('%d/%m a las %H:%M')}"
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ocurrió un error. Intentá de nuevo.")


def main():
    scheduler.start()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("lista", lista))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot iniciado")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
