import logging
import openai
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    CommandHandler,
    filters,
)
import os
import re

# 🛡️ Logging setup
logging.basicConfig(level=logging.INFO)

# ✅ Set your OpenAI API key and Telegram Bot Token
openai.api_key = "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"
BOT_TOKEN = "8051814176:AAEZhLo7ZXPTT4dezcvoyIn51Ns13YyRZMM"

# 🟢 /start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"👋 *Welcome to Impossible AI Bot!*\n\n"
        f"📜 I can generate code scripts in the following languages:\n"
        f"`Python`, `JavaScript`, `C++`, `Bash`, `Telegram Bots`, `HTML`, `CSS`\n\n"
        f"⭐ *VIP Feature Unlocked!*\n"
        f"👤 Created by [{user.full_name}](tg://user?id={only_possible})\n\n"
        f"_Just type your script request like:_ `Telegram bot to ban users`"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

# 🟢 Handle greetings like hi, hello, etc.
async def handle_greeting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    await update.message.reply_text(f"👋 Hello {user}! I'm here to write your code scripts. What can I help you with?")

# 🟢 Handle code request and respond with OpenAI result
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text or ""

    # greetings skip from script generation
    if re.match(r"(?i)^(hi|hello|salam|hey|aslam o alaikum|how are you)$", user_msg.strip()):
        return await handle_greeting(update, context)

    prompt = f"""You are a professional code generator assistant. The user is asking for a code snippet or a script. 
Only reply with the requested code script without any explanation or intro. Supported languages: Python, JavaScript, C++, Bash, Telegram bot, etc.

User Request: {user_msg}
    
Your Reply (only script):"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
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
        await update.message.reply_text("❌ OpenAI سے جواب حاصل کرنے میں مسئلہ پیش آیا۔")

# 🤖 Start the bot
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^(hi|hello|salam|aslam o alaikum|how are you|hey)$"), handle_greeting))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 AI Script Generator Bot is running...")
    app.run_polling()