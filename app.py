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
def get_next_weekday(weekday: int) -> datetime:
today = datetime.now()
days_ahead = weekday - today.weekday()
if days_ahead <= 0:
days_ahead += 7
return today + timedelta(days=days_ahead)
def parse_reminder(text: str):
text = text.lower().strip()
now = datetime.now()
dias = {
"lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2,
"jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6
}
# Extraer hora
hora_match = re.search(r'(\d{1,2}):?(\d{2})?\s*(am|pm)?', text)
if not hora_match:
return None, None
hora = int(hora_match.group(1))
minuto = int(hora_match.group(2)) if hora_match.group(2) else 0
ampm = hora_match.group(3)
if ampm == "pm" and hora < 12:
hora += 12
elif ampm == "am" and hora == 12:
hora = 0
# Extraer fecha
fecha = None
if "hoy" in text:
fecha = now.replace(hour=hora, minute=minuto, second=0, microsecond=0)
elif "mañana" in text or "manana" in text:
fecha = (now + timedelta(days=1)).replace(hour=hora, minute=minuto, second=0, microse
else:
for dia, num in dias.items():
if dia in text:
break
fecha = get_next_weekday(num).replace(hour=hora, minute=minuto, second=0, mic
if fecha is None:
fecha = now.replace(hour=hora, minute=minuto, second=0, microsecond=0)
# Extraer tarea
tarea = text
for palabra in ["recordame", "recuérdame", "recordar", "recordatorio", "hoy", "mañana", "
"el lunes", "el martes", "el miércoles", "el miercoles", "el jueves",
"el viernes", "el sábado", "el sabado", "el domingo",
"lunes", "martes", "miércoles", "miercoles", "jueves", "viernes", "sábado
"a las", "las", "a la"]:
tarea = tarea.replace(palabra, "")
tarea = re.sub(r'\d{1,2}:?\d{0,2}\s*(am|pm)?', '', tarea)
tarea = re.sub(r'\s+', ' ', tarea).strip()
if not tarea:
tarea = "Recordatorio"
return fecha, tarea.capitalize()
async def send_reminder(bot, chat_id: int, tarea: str):
await bot.send_message(chat_id=chat_id, text=f" Recordatorio: {tarea}")
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text(
" Hola! Soy tu bot de recordatorios.\n\n"
"Escribime algo como:\n"
"• el lunes a las 11 recordame comprar camiseta\n"
"• mañana a las 9 llamar al médico\n"
"• hoy a las 15 reunión con cliente\n\n"
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
fecha, tarea = parse_reminder(text)
if fecha is None:
await update.message.reply_text(
" No entendí la hora. Probá con:\n"
"el lunes a las 11 recordame comprar camiseta"
)
return
if fecha <= datetime.now():
await update.message.reply_text(" return
Esa fecha y hora ya pasaron. Usá una hora futura.
job_id = f"{chat_id}_{fecha.strftime('%Y%m%d%H%M')}_{tarea[:10]}"
scheduler.add_job(
send_reminder, "date",
run_date=fecha,
args=[context.bot, chat_id, tarea],
id=job_id,
replace_existing=True
)
dias_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
dia = dias_es[fecha.weekday()]
await update.message.reply_text(
f" Recordatorio guardado\n"
f" {tarea}\n"
f" {dia} {fecha.strftime('%d/%m')} a las {fecha.strftime('%H:%M')}"
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
