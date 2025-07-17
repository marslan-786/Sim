import logging
import openai
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters,
)
import os

# 🔐 اپنی OpenAI API key یہاں لگائیں
openai.api_key = "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"

# 🔐 اپنا Telegram Bot Token یہاں ڈالیں
BOT_TOKEN = "8051814176:AAEZhLo7ZXPTT4dezcvoyIn51Ns13YyRZMM"

# لاگنگ سیٹ اپ
logging.basicConfig(level=logging.INFO)

# ✨ صرف کوڈ سکرپٹ کا جواب دینے والا فنکشن
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text or ""

    prompt = f"""You are a professional code generator assistant. The user is asking for a code snippet or a script. 
Only reply with the requested code script without any explanation or intro. Supported languages: Python, JavaScript, C++, Bash, Telegram bot, etc.

User Request: {user_msg}
    
Your Reply (only script):"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # اگر GPT-4 چاہیے تو یہاں تبدیل کریں
            messages=[
                {"role": "system", "content": "You only generate clean scripts."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=1500,
        )

        script_code = response.choices[0].message.content.strip()
        await update.message.reply_text(f"```\n{script_code}\n```", parse_mode="Markdown")

    except Exception as e:
        logging.error(f"OpenAI Error: {e}")
        await update.message.reply_text("❌ کوئی غلطی ہوئی۔")

# 🤖 بوٹ شروع کریں
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 AI Code Generator Bot is running...")
    app.run_polling()