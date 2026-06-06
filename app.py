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


def parse_reminder_with_claude(text: str) -> dict:
    now = datetime.now()
    prompt = f"""Sos un asistente que parsea recordatorios en español.
El usuario manda un mensaje y vos tenés que extraer la tarea y la fecha/hora.

Fecha y hora actual: {now.strftime("%Y-%m-%d %H:%M")} (día: {now.strftime("%A")})

Mensaje del usuario: "{text}"

Respondé SOLO con JSON válido, sin texto extra, sin markdown:
{{
  "tarea": "descripción de la tarea",
  "datetime": "YYYY-MM-DD HH:MM",
  "valido": true,
  "error": ""
}}

Reglas:
- "el lunes" = próximo lunes
- "mañana" = mañana
- "hoy" = hoy
- Si no dice hora, usá 09:00
- Si la fecha ya pasó, poné valido: false con error explicando
- Días: Monday=lunes, Tuesday=martes, Wednesday=miércoles, Thursday=jueves, Friday=viernes, Saturday=sábado, Sunday=domingo"""

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text.strip()
    return json.loads(raw)


async def send_reminder(bot, chat_id: int, tarea: str):
    await bot.send_message(
        chat_id=chat_id,
        text=f"🔔 *Recordatorio*\n\n{tarea}",
        parse_mode="Markdown"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 ¡Hola! Soy tu bot de recordatorios.\n\n"
        "Decime cosas como:\n"
        "• _el lunes a las 11 recordame comprar camiseta_\n"
        "• _mañana a las 9 llamar al médico_\n"
        "• _hoy a las 18 reunión con cliente_\n\n"
        "Y te recuerdo a tiempo ⏰",
        parse_mode="Markdown"
    )


async def lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.message.chat_id

    await update.message.reply_text("⏳ Procesando tu recordatorio...")

    try:
        parsed = parse_reminder_with_claude(text)

        if not parsed.get("valido", False):
            error = parsed.get("error", "No pude entender el recordatorio.")
            await update.message.reply_text(
                f"❌ {error}\n\nIntentá con algo como: _el lunes a las 11 comprar camiseta_",
                parse_mode="Markdown"
            )
            return

        tarea = parsed["tarea"]
        dt_str = parsed["datetime"]
        reminder_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")

        if reminder_dt <= datetime.now():
            await update.message.reply_text("❌ Esa fecha ya pasó. Probá con una futura.")
            return

        job_id = f"{chat_id}_{dt_str.replace(' ','_').replace(':','')}_{tarea[:15]}"
        scheduler.add_job(
            send_reminder,
            "date",
            run_date=reminder_dt,
            args=[context.bot, chat_id, tarea],
            id=job_id,
            replace_existing=True
        )

        dias = {
            "Monday": "lunes", "Tuesday": "martes", "Wednesday": "miércoles",
            "Thursday": "jueves", "Friday": "viernes", "Saturday": "sábado", "Sunday": "domingo"
        }
        dia_es = dias.get(reminder_dt.strftime("%A"), reminder_dt.strftime("%A"))
        fecha_legible = f"{dia_es} {reminder_dt.strftime('%d/%m')} a las {reminder_dt.strftime('%H:%M')}"

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


def main():
    scheduler.start()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("lista", lista))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot iniciado...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
