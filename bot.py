import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from datetime import datetime, timedelta
import re
from typing import Dict, Set, List

# لوگنگ سیٹ اپ
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ڈیٹا بیس
group_settings: Dict[str, dict] = {}
user_warnings: Dict[str, dict] = {}
action_settings: Dict[str, dict] = {}
user_chats: Dict[int, Dict[str, Set[str]]] = {}
admin_list: Dict[str, List[int]] = {}

# دورانیہ کی تبدیلی کے لیے فنکشنز
def parse_duration(duration_str: str) -> timedelta:
    durations = {
        '30m': timedelta(minutes=30),
        '1h': timedelta(hours=1),
        '6h': timedelta(hours=6),
        '1d': timedelta(days=1),
        '3d': timedelta(days=3),
        '7d': timedelta(days=7)
    }
    return durations.get(duration_str, timedelta(hours=1))

def format_duration(duration: timedelta) -> str:
    if duration.days >= 1:
        return f"{duration.days} دن"
    hours = duration.seconds // 3600
    if hours >= 1:
        return f"{hours} گھنٹے"
    return f"{duration.seconds // 60} منٹ"

# گروپ سیٹنگز انیشیلائزیشن
def initialize_group_settings(chat_id: str, chat_type: str = "group"):
    if chat_id not in group_settings:
        group_settings[chat_id] = {
            "block_links": False,
            "block_forwards": False,
            "remove_forward_tag": False,
            "allowed_domains": set(),
            "chat_type": chat_type
        }
    if chat_id not in action_settings:
        action_settings[chat_id] = {
            "links": {
                "action": "delete",
                "duration": "1h",
                "warn": True,
                "delete": True,
                "enabled": False
            },
            "forward": {
                "action": "delete",
                "duration": "1h",
                "warn": True,
                "delete": True,
                "enabled": False
            }
        }
    if chat_id not in admin_list:
        admin_list[chat_id] = []

# ایڈمن چیک کرنے کا فنکشن
async def is_admin(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        return any(admin.user.id == user_id for admin in admins)
    except Exception as e:
        logger.error(f"Admin check failed: {e}")
        return False

# یوزر چاٹس انیشیلائزیشن
def initialize_user_chats(user_id: int):
    if user_id not in user_chats:
        user_chats[user_id] = {"groups": set(), "channels": set()}

# بوٹ ہینڈلرز
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    initialize_user_chats(user_id)
    
    if update.message.chat.type == "private":
        keyboard = [
            [InlineKeyboardButton("➕ گروپ میں شامل کریں", url=f"https://t.me/{context.bot.username}?startgroup=true")],
            [InlineKeyboardButton("📊 میرے گروپس", callback_data="your_groups")],
            [InlineKeyboardButton("📢 میرے چینلز", callback_data="your_channels")],
            [InlineKeyboardButton("❓ مدد", callback_data="help_command")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "👋 گروپ مینیجمنٹ بوٹ میں خوش آمدید!\n\n"
            "🔹 گروپ/چینل میں شامل کریں\n"
            "🔹 سیٹنگز کو ترتیب دیں\n"
            "🔹 جدید انتظامی ٹولز",
            reply_markup=reply_markup
        )
    else:
        chat_id = str(update.message.chat.id)
        chat_type = "channel" if update.message.chat.type == "channel" else "group"
        initialize_user_chats(user_id)
        user_chats[user_id][f"{chat_type}s"].add(chat_id)
        initialize_group_settings(chat_id, chat_type)
        await show_help(update, context)

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🤖 *بوٹ کمانڈز*:

*ایڈمن کمانڈز*:
/ban [وقت] - صارف کو بین کریں (جوابی پیغام پر)
/mute [وقت] - صارف کو میوٹ کریں (جوابی پیغام پر)
/warn - صارف کو وارننگ دیں (جوابی پیغام پر)
/unban - صارف کو انبین کریں
/unmute - صارف کو انمیوٹ کریں
/settings - سیٹنگز ترتیب دیں
/allowlink [ڈومین] - ڈومین کی اجازت دیں
/blocklink [ڈومین] - ڈومین کو بلاک کریں

مثالیں:
/ban 1h - 1 گھنٹے کے لیے بین کریں
/mute 2d - 2 دن کے لیے میوٹ کریں
"""
    if isinstance(update, Update):
        await update.message.reply_text(help_text, parse_mode="Markdown")
    else:
        await update.edit_message_text(help_text, parse_mode="Markdown")

async def group_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.message.chat
    user = update.effective_user
    
    if not await is_admin(chat.id, user.id, context):
        await update.message.reply_text("⚠️ صرف ایڈمن اس کمانڈ کو استعمال کر سکتے ہیں!")
        return
        
    group_id = str(chat.id)
    if chat.type == "channel":
        await show_channel_settings(update, group_id)
    else:
        await show_group_settings(update, group_id)

async def show_group_settings(update_or_query, group_id: str):
    initialize_group_settings(group_id)
    
    keyboard = [
        [InlineKeyboardButton("🔗 لنک سیٹنگز", callback_data=f"link_settings_{group_id}")],
        [InlineKeyboardButton("↩️ فارورڈ سیٹنگز", callback_data=f"forward_settings_{group_id}")],
        [InlineKeyboardButton("⚠️ وارننگ سسٹم", callback_data=f"warning_settings_{group_id}")],
        [InlineKeyboardButton("🔙 واپس", callback_data="your_groups")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "⚙️ *گروپ سیٹنگز*\n\nترتیب دینے کے لیے زمرہ منتخب کریں:"
    
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update_or_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def show_link_settings(query, group_id: str):
    initialize_group_settings(group_id)
    settings = action_settings[group_id]["links"]
    
    action = settings["action"].capitalize()
    duration = settings["duration"]
    warn = "✅" if settings["warn"] else "❌"
    enabled = "✅" if settings["enabled"] else "❌"
    
    keyboard = [
        [InlineKeyboardButton(f"🔘 فعال: {enabled}", callback_data=f"toggle_links_enabled_{group_id}")],
        [InlineKeyboardButton(f"⚡ کارروائی: {action}", callback_data=f"cycle_link_action_{group_id}")],
        [InlineKeyboardButton(f"⏱ دورانیہ: {duration}", callback_data=f"change_link_duration_{group_id}")],
        [InlineKeyboardButton(f"⚠️ وارننگ: {warn}", callback_data=f"toggle_link_warn_{group_id}")],
        [InlineKeyboardButton("✏️ اجازت شدہ ڈومینز", callback_data=f"edit_domains_{group_id}")],
        [InlineKeyboardButton("🔙 واپس", callback_data=f"group_{group_id}")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🔗 *لنک سیٹنگز*\n\nلنکس کو کیسے ہینڈل کیا جائے:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def show_user_groups(query):
    user_id = query.from_user.id
    initialize_user_chats(user_id)
    
    if not user_chats[user_id]["groups"]:
        keyboard = [[InlineKeyboardButton("🔙 واپس", callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📊 *میرے گروپس*\n\nآپ نے مجھے کسی گروپ میں شامل نہیں کیا ہے!",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return
    
    keyboard = []
    for group_id in user_chats[user_id]["groups"]:
        try:
            chat = await query.bot.get_chat(int(group_id))
            keyboard.append([InlineKeyboardButton(chat.title, callback_data=f"group_{group_id}")])
        except Exception as e:
            logger.warning(f"گروپ معلومات حاصل نہیں ہو سکی {group_id}: {e}")
    
    keyboard.append([InlineKeyboardButton("🔙 واپس", callback_data="start")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "📊 *میرے گروپس*\n\nترتیب دینے کے لیے گروپ منتخب کریں:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    try:
        if data == "start":
            await start(update, context)
        elif data == "your_groups":
            await show_user_groups(query)
        elif data == "your_channels":
            await show_user_channels(query)
        elif data == "help_command":
            await show_help(query, context)
        elif data.startswith("group_"):
            group_id = data.split("_")[1]
            if await is_admin(int(group_id), query.from_user.id, context):
                await show_group_settings(query, group_id)
            else:
                await query.answer("⚠️ صرف ایڈمن یہ سیٹنگز دیکھ سکتے ہیں!", show_alert=True)
        elif data.startswith("toggle_links_enabled_"):
            group_id = data.split("_")[3]
            if await is_admin(int(group_id), query.from_user.id, context):
                action_settings[group_id]["links"]["enabled"] = not action_settings[group_id]["links"]["enabled"]
                await show_link_settings(query, group_id)
            else:
                await query.answer("⚠️ صرف ایڈمن یہ تبدیلی کر سکتے ہیں!", show_alert=True)
        elif data.startswith("cycle_link_action_"):
            group_id = data.split("_")[3]
            if await is_admin(int(group_id), query.from_user.id, context):
                actions = ["delete", "mute", "ban"]
                current = action_settings[group_id]["links"]["action"]
                next_action = actions[(actions.index(current) + 1) % len(actions)]
                action_settings[group_id]["links"]["action"] = next_action
                await show_link_settings(query, group_id)
            else:
                await query.answer("⚠️ صرف ایڈمن یہ تبدیلی کر سکتے ہیں!", show_alert=True)
        elif data.startswith("change_link_duration_"):
            group_id = data.split("_")[3]
            if await is_admin(int(group_id), query.from_user.id, context):
                durations = ["30m", "1h", "6h", "1d", "3d", "7d"]
                current = action_settings[group_id]["links"]["duration"]
                next_duration = durations[(durations.index(current) + 1) % len(durations)]
                action_settings[group_id]["links"]["duration"] = next_duration
                await show_link_settings(query, group_id)
            else:
                await query.answer("⚠️ صرف ایڈمن یہ تبدیلی کر سکتے ہیں!", show_alert=True)
        elif data == "back":
            await start(update, context)
    except Exception as e:
        logger.error(f"بٹن ہینڈلر میں خرابی: {e}")
        await query.edit_message_text("❌ ایک خرابی پیش آئی۔ براہ کرم دوبارہ کوشش کریں۔")

async def message_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
        
    message = update.message
    chat_id = str(message.chat.id)
    chat_type = "channel" if message.chat.type == "channel" else "group"
    initialize_group_settings(chat_id, chat_type)
    
    # چینل کے لیے خاص ہینڈلنگ
    if chat_type == "channel":
        if group_settings[chat_id]["remove_forward_tag"] and message.forward_from_chat:
            try:
                await message.edit_forward_sender_name(None)
            except Exception as e:
                logger.warning(f"فارورڈ ٹیگ ہٹانے میں ناکامی: {e}")
        return
    
    # گروپ ہینڈلنگ
    if message.forward_date and group_settings[chat_id]["block_forwards"]:
        await handle_violation(update, context, "forward")
        return
    
    if group_settings[chat_id]["block_links"]:
        entities = message.entities or []
        text = message.text or ""
        for entity in entities:
            if entity.type in ["url", "text_link"]:
                url = text[entity.offset:entity.offset + entity.length] if entity.type == "url" else entity.url
                if not any(domain in url for domain in group_settings[chat_id]["allowed_domains"]):
                    await handle_violation(update, context, "links")
                    break

async def handle_violation(update: Update, context: ContextTypes.DEFAULT_TYPE, violation_type: str):
    message = update.message
    chat_id = str(message.chat.id)
    user_id = message.from_user.id
    actions = action_settings.get(chat_id, {}).get(violation_type, {})
    
    if not actions.get("enabled", False):
        return
    
    try:
        if actions.get("delete", True):
            await message.delete()
    except Exception as e:
        logger.warning(f"پیغام ڈیلیٹ کرنے میں ناکامی: {e}")
    
    if actions.get("warn", True):
        await warn_user(update, context)
    
    action = actions.get("action", "delete")
    duration = parse_duration(actions.get("duration", "1h"))
    
    try:
        if action == "mute":
            until_date = datetime.now() + duration
            await context.bot.restrict_chat_member(
                chat_id=int(chat_id),
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date
            )
            await context.bot.send_message(
                chat_id=int(chat_id),
                text=f"🔇 صارف کو {format_duration(duration)} کے لیے میوٹ کر دیا گیا"
            )
        elif action == "ban":
            until_date = datetime.now() + duration
            await context.bot.ban_chat_member(
                chat_id=int(chat_id),
                user_id=user_id,
                until_date=until_date
            )
            await context.bot.send_message(
                chat_id=int(chat_id),
                text=f"🚫 صارف کو {format_duration(duration)} کے لیے بین کر دیا گیا"
            )
    except Exception as e:
        logger.error(f"کارروائی {action} کرنے میں ناکامی: {e}")

# بوٹ چلانے کا حصہ
if __name__ == "__main__":
    TOKEN = "7735984673:AAGEhbsdIfO-j8B3DvBwBW9JSb9BcPd_J6o"
    app = ApplicationBuilder().token(TOKEN).build()

    # ہینڈلرز شامل کریں
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", show_help))
    app.add_handler(CommandHandler("settings", group_settings_command))
    app.add_handler(MessageHandler(filters.ALL, message_filter))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 بوٹ چل رہا ہے...")
    app.run_polling()
