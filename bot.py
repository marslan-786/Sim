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

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Simulated databases
group_settings = {}
user_warnings = {}
action_settings = {}

def parse_duration(duration_str):
    number = int(re.findall(r'\d+', duration_str)[0])
    if 'h' in duration_str:
        return timedelta(hours=number)
    elif 'm' in duration_str:
        return timedelta(minutes=number)
    elif 'd' in duration_str:
        return timedelta(days=number)
    else:
        return timedelta(hours=1)

def initialize_group_settings(group_id):
    if group_id not in group_settings:
        group_settings[group_id] = {
            "block_links": False,
            "block_forwards": False,
            "allowed_domains": set()
        }
    if group_id not in action_settings:
        action_settings[group_id] = {
            "links": {"action": "delete", "duration": "1h", "warn": True, "delete": True},
            "forward": {"action": "ban", "duration": "1h", "warn": True, "delete": True}
        }
    if group_id not in user_warnings:
        user_warnings[group_id] = {}

# ----------- Bot Handlers -----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == "private":
        keyboard = [
            [InlineKeyboardButton("➕ Add me to Group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
            [InlineKeyboardButton("📊 Your Groups", callback_data="your_groups")],
            [InlineKeyboardButton("📢 Your Channels", callback_data="your_channels")],
            [InlineKeyboardButton("❓ Help", callback_data="help_command")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "👋 Welcome to Ultimate Group Manager Bot!\n\n"
            "🔹 Add me to your group/channel\n"
            "🔹 Configure group settings\n"
            "🔹 Powerful moderation tools",
            reply_markup=reply_markup
        )
    else:
        await show_help(update, context)

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🤖 *Bot Commands*:

*Group Admin Commands*:
/ban - Ban a user (reply to message)
/mute - Mute a user (reply to message)
/warn - Warn a user (reply to message)
/unban - Unban a user
/unmute - Unmute a user
/settings - Configure group settings
/allowlink [domain] - Allow specific domain
/blocklink [domain] - Block specific domain

*User Commands*:
/help - Show this help message
"""
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def group_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.message.chat
    group_id = str(chat.id)
    if chat.type == "channel":
        await show_channel_settings(update, group_id)
    else:
        await show_group_settings(update, group_id)

async def show_group_settings(update_or_query, group_id):
    initialize_group_settings(group_id)
    keyboard = [
        [InlineKeyboardButton("🔗 Link Settings", callback_data=f"link_settings_{group_id}")],
        [InlineKeyboardButton("👥 Mention Settings", callback_data=f"mention_settings_{group_id}")],
        [InlineKeyboardButton("↩️ Forward Settings", callback_data=f"forward_settings_{group_id}")],
        [InlineKeyboardButton("⚠️ Warning System", callback_data=f"warning_settings_{group_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="your_groups")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "⚙️ *Group Settings*\n\nSelect category to configure:"
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update_or_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def show_channel_settings(update_or_query, channel_id):
    initialize_group_settings(channel_id)
    keyboard = [
        [InlineKeyboardButton("↩️ Remove Forward Tag", callback_data=f"channel_fwd_{channel_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="your_channels")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "📢 *Channel Settings*\n\nConfigure forwarding behavior:"
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update_or_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "your_groups":
        await show_user_groups(query)
    elif data == "your_channels":
        await show_user_channels(query)
    elif data == "help_command":
        await show_help(query, context)
    elif data.startswith("group_"):
        group_id = data.split("_")[1]
        await show_group_settings(query, group_id)
    elif data.startswith("channel_"):
        channel_id = data.split("_")[1]
        await show_channel_settings(query, channel_id)
    elif data.startswith("link_settings_"):
        group_id = data.split("_")[2]
        await query.edit_message_text(f"⚙️ Link settings panel for group {group_id} (demo)")

async def message_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = str(message.chat_id)
    initialize_group_settings(chat_id)

    if message.chat.type not in ['group', 'supergroup']:
        return

    if message.forward_date and group_settings[chat_id].get("block_forwards", False):
        await handle_violation(update, context, "forward")
        return

    if group_settings[chat_id].get("block_links", False):
        entities = message.entities or []
        text = message.text or ""
        for entity in entities:
            if entity.type == "url" or entity.type == "text_link":
                url = ""
                if entity.type == "url":
                    url = text[entity.offset: entity.offset + entity.length]
                elif entity.type == "text_link":
                    url = entity.url
                domain_allowed = any(domain in url for domain in group_settings[chat_id]["allowed_domains"])
                if not domain_allowed:
                    await handle_violation(update, context, "links")
                    break

async def handle_violation(update: Update, context: ContextTypes.DEFAULT_TYPE, violation_type):
    chat_id = str(update.message.chat_id)
    user_id = update.message.from_user.id
    actions = action_settings.get(chat_id, {}).get(violation_type, {})
    if actions.get("delete", True):
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"Delete failed: {e}")

    if actions.get("warn", True):
        await warn_user(update, context)

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    user_id = update.message.from_user.id
    initialize_group_settings(chat_id)
    warns = user_warnings[chat_id].get(user_id, 0) + 1
    user_warnings[chat_id][user_id] = warns
    await update.message.reply_text(f"⚠️ User {update.message.from_user.first_name} warned! Total: {warns}")
    if warns >= 3:
        await update.message.reply_text(f"🚫 User banned due to 3 warnings.")
        try:
            await context.bot.ban_chat_member(chat_id=int(chat_id), user_id=user_id)
            user_warnings[chat_id][user_id] = 0
        except Exception as e:
            await update.message.reply_text(f"Failed to ban user: {e}")

async def show_user_groups(query):
    keyboard = [
        [InlineKeyboardButton("Group 1", callback_data="group_12345")],
        [InlineKeyboardButton("Group 2", callback_data="group_67890")],
        [InlineKeyboardButton("🔙 Back", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("📊 *Your Groups*\n\nSelect a group:", reply_markup=reply_markup, parse_mode="Markdown")

async def show_user_channels(query):
    keyboard = [
        [InlineKeyboardButton("Channel 1", callback_data="channel_11111")],
        [InlineKeyboardButton("Channel 2", callback_data="channel_22222")],
        [InlineKeyboardButton("🔙 Back", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("📢 *Your Channels*\n\nSelect a channel:", reply_markup=reply_markup, parse_mode="Markdown")

# ---------------- RUN BOT ------------------

if __name__ == "__main__":
    TOKEN = "7735984673:AAGEhbsdIfO-j8B3DvBwBW9JSb9BcPd_J6o"
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", show_help))
    app.add_handler(CommandHandler("settings", group_settings_command))
    app.add_handler(MessageHandler(filters.ALL, message_filter))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot is running...")
    app.run_polling()
