import os
import json
import asyncio
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

scheduler = AsyncIOScheduler(jobstores={"default": MemoryJobStore()})


def parse_reminder_with_claude(text: str) -> dict:
    """Use Claude to parse natural language reminder in Spanish."""
    now = datetime.now()
    prompt = f"""Sos un asistente que parsea recordatorios en español.
El usuario manda un mensaje y vos tenés que extraer:
- La tarea o cosa a recordar
- La fecha y hora del recordatorio

Fecha y hora actual: {now.strftime("%Y-%m-%d %H:%M")} (día: {now.strftime("%A")})

Mensaje del usuario: "{text}"

Respondé SOLO con un JSON válido, sin texto extra, sin markdown, sin explicaciones:
{{
  "tarea": "descripción de la tarea",
  "datetime": "YYYY-MM-DD HH:MM",
  "valido": true/false,
  "error": "mensaje de error si no se pudo parsear"
}}

Reglas para interpretar fechas:
- "el lunes" = próximo lunes
- "mañana" = {(now.replace(day=now.day+1)).strftime("%Y-%m-%d")}
- "hoy" = {now.strftime("%Y-%m-%d")}
- Si no dice hora, usá 09:00
- Si no dice fecha, asumí hoy
- Si el datetime ya pasó, poné valido: false con error explicando

Días de la semana en inglés: Monday=lunes, Tuesday=martes, Wednesday=miércoles, Thursday=jueves, Friday=viernes, Saturday=sábado, Sunday=domingo"""

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    return json.loads(raw)


async def send_reminder(bot, chat_id: int, tarea: str):
    """Send the reminder message to the user."""
    await bot.send_message(
        chat_id=chat_id,
        text=f"🔔 *Recordatorio*\n\n{tarea}",
        parse_mode="Markdown"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 ¡Hola! Soy tu bot de recordatorios.\n\n"
        "Podés decirme cosas como:\n"
        "• _\"el lunes a las 11 recordame comprar camiseta\"_\n"
        "• _\"mañana a las 9 llamar al médico\"_\n"
        "• _\"hoy a las 18 reunión con cliente\"_\n\n"
        "¡Y te lo recuerdo a tiempo! ⏰",
        parse_mode="Markdown"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.message.chat_id

    await update.message.reply_text("⏳ Procesando tu recordatorio...")

    try:
        parsed = parse_reminder_with_claude(text)

        if not parsed.get("valido", False):
            error = parsed.get("error", "No pude entender el recordatorio.")
            await update.message.reply_text(f"❌ {error}\n\nIntentá con algo como: _\"el lunes a las 11 comprar camiseta\"_", parse_mode="Markdown")
            return

        tarea = parsed["tarea"]
        dt_str = parsed["datetime"]
        reminder_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")

        if reminder_dt <= datetime.now():
            await update.message.reply_text("❌ Esa fecha y hora ya pasaron. Probá con una futura.")
            return

        job_id = f"{chat_id}_{dt_str}_{tarea[:20]}"
        scheduler.add_job(
            send_reminder,
            "date",
            run_date=reminder_dt,
            args=[context.bot, chat_id, tarea],
            id=job_id,
            replace_existing=True
        )

        fecha_legible = reminder_dt.strftime("%A %d/%m a las %H:%M")
        await update.message.reply_text(
            f"✅ *Recordatorio guardado*\n\n"
            f"📌 {tarea}\n"
            f"📅 {fecha_legible}",
            parse_mode="Markdown"
        )

    except json.JSONDecodeError:
        await update.message.reply_text("❌ No pude procesar el mensaje. Intentá de nuevo.")
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Ocurrió un error. Intentá de nuevo.")


async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    jobs = [j for j in scheduler.get_jobs() if str(chat_id) in j.id]

    if not jobs:
        await update.message.reply_text("📭 No tenés recordatorios activos.")
        return

    msg = "📋 *Tus recordatorios activos:*\n\n"
    for job in jobs:
        run_date = job.next_run_time.strftime("%d/%m a las %H:%M")
        tarea = job.args[2]
        msg += f"• {tarea} — {run_date}\n"

    await update.message.reply_text(msg, parse_mode="Markdown")


def main():
    scheduler.start()

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("lista", list_reminders))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot iniciado...")
    app.run_polling()


if __name__ == "__main__":
    main()
