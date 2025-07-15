import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

BOT_TOKEN = "8017193630:AAFaMRpJ7Hk-2MTibaWOR_71-NYuFgr_2_U"
API_URL = "https://legendxdata.site/Api/simdata.php?phone="

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()

    if not phone.isdigit() or len(phone) < 10:
        await update.message.reply_text("❌ براہ کرم درست فون نمبر درج کریں (صرف ہندسے)")
        return

    await update.message.reply_text("📡 ڈیٹا حاصل کیا جا رہا ہے...")

    try:
        response = requests.get(API_URL + phone)
        data = response.json()

        if isinstance(data, list) and len(data) > 0:
            record = data[0]

            # Capital case keys جیسا API دے رہا ہے
            name = record.get("Name", "N/A")
            number = record.get("Number", "N/A")
            cnic = record.get("CNIC", "N/A")
            operator = record.get("Operator", "N/A")
            address = record.get("Address", "N/A")

            message = f"""📄 *SIM Information:*

👤 *Name:* `{name}`
☎️ *Number:* `{number}`
🪪 *CNIC:* `{cnic}`
📶 *Operator:* `{operator}`
📍 *Address:* `{address}`
"""
            await update.message.reply_markdown(message)
        else:
            await update.message.reply_text("⚠️ اس نمبر کا کوئی ریکارڈ نہیں ملا۔")

    except Exception as e:
        await update.message.reply_text("❌ خرابی پیش آئی:\n" + str(e))

# بوٹ بنائیں اور اسٹارٹ کریں
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.run_polling()
