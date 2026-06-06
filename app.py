import os
import re
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
scheduler = AsyncIOScheduler()


def get_next_weekday(weekday):
    today = datetime.now()
    days_ahead = weekday - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


def parse_reminder(text):
    text_lower = text.lower().strip()
    now = datetime.now()

    dias = {
        "lunes": 0, "martes": 1, "miercoles": 2,
        "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6
    }

    hora_match = re.search(r'(\d{1,2}):?(\d{2})?\s*(am|pm)?', text_lower)
    if not hora_match:
        return None, None

    hora = int(hora_match.group(1))
    minuto = int(hora_match.group(2)) if hora_match.group(2) else 0
    ampm = hora_match.group(3)

    if ampm == "pm" and hora < 12:
        hora += 12
    elif ampm == "am" and hora == 12:
        hora = 0

    fecha = None
    if "hoy" in text_lower:
        fecha = now.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    elif "manana" in text_lower or "mañana" in text_lower:
        fecha = (now + timedelta(days=1)).replace(hour=hora, minute=minuto, second=0, microsecond=0)
    else:
        for dia, num in dias.items():
            if dia in text_lower:
                fecha = get_next_weekday(num).replace(hour=hora, minute=minuto, second=0, microsecond=0)
                break

    if fecha is None:
        fecha = now.replace(hour=hora, minute=minuto, second=0, microsecond=0)

    tarea = text_lower
    palabras = ["recordame", "recuerdame", "recordar", "recordatorio",
                "hoy", "manana", "mañana", "a las", "las", "a la",
                "el lunes", "el martes", "el miercoles", "el jueves",
                "el viernes", "el sabado", "el domingo",
                "lunes", "martes", "miercoles", "jueves",
                "viernes", "sabado", "domingo"]
    for p in palabras:
        tarea = tarea.replace(p, "")

    tarea = re.sub(r'\d{1,2}:?\d{0,2}\s*(am|pm)?', '', tarea)
    tarea = re.sub(r'\s+', ' ', tarea).strip()

    if not tarea:
        tarea = "Recordatorio"

    return fecha, tarea.capitalize()


async def send_reminder(bot, chat_id, tarea):
    await bot.send_message(chat_id=chat_id, text="Recordatorio: " + tarea)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hola! Soy tu bot de recordatorios.\n\n"
        "Escribime algo como:\n"
        "el lunes a las 11 recordame comprar camiseta\n"
        "manana a las 9 llamar al medico\n"
        "hoy a las 15 reunion con cliente\n\n"
        "Usa /lista para ver tus recordatorios activos."
    )


async def lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    jobs = [j for j in scheduler.get_jobs() if str(chat_id) in j.id]
    if not jobs:
        await update.message.reply_text("No tenes recordatorios activos.")
        return
    msg = "Tus recordatorios:\n\n"
    for job in jobs:
        msg += "- " + job.args[2] + " - " + job.next_run_time.strftime('%d/%m %H:%M') + "\n"
    await update.message.reply_text(msg)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.message.chat_id

    fecha, tarea = parse_reminder(text)

    if fecha is None:
        await update.message.reply_text(
            "No entendi la hora. Proba con:\n"
            "el lunes a las 11 recordame comprar camiseta"
        )
        return

    if fecha <= datetime.now():
        await update.message.reply_text("Esa hora ya paso. Usa una hora futura.")
        return

    job_id = str(chat_id) + "_" + fecha.strftime('%Y%m%d%H%M') + "_" + tarea[:10].replace(" ", "")
    scheduler.add_job(
        send_reminder, "date",
        run_date=fecha,
        args=[context.bot, chat_id, tarea],
        id=job_id,
        replace_existing=True
    )

    dias_es = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    dia = dias_es[fecha.weekday()]

    await update.message.reply_text(
        "Recordatorio guardado!\n"
        "Tarea: " + tarea + "\n"
        "Cuando: " + dia + " " + fecha.strftime('%d/%m') + " a las " + fecha.strftime('%H:%M')
    )


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
