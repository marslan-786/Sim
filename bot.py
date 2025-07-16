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
from typing import Dict, Set

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Databases
group_settings: Dict[str, dict] = {}
user_warnings: Dict[str, dict] = {}
action_settings: Dict[str, dict] = {}
user_chats: Dict[int, Dict[str, Set[str]]] = {}  # {user_id: {"groups": set(), "channels": set()}}

def parse_duration(duration_str: str) -> timedelta:
    """Parse duration string like 1h, 2d, 30m into timedelta"""
    if not duration_str:
        return timedelta(hours=1)
    
    try:
        number = int(re.findall(r'\d+', duration_str)[0])
        if 'h' in duration_str:
            return timedelta(hours=number)
        elif 'm' in duration_str:
            return timedelta(minutes=number)
        elif 'd' in duration_str:
            return timedelta(days=number)
    except (IndexError, ValueError):
        pass
    return timedelta(hours=1)

def format_duration(duration: timedelta) -> str:
    """Format timedelta into human-readable string"""
    if duration.days > 0:
        return f"{duration.days}d"
    hours = duration.seconds // 3600
    if hours > 0:
        return f"{hours}h"
    return f"{duration.seconds // 60}m"

def initialize_user_chats(user_id: int):
    if user_id not in user_chats:
        user_chats[user_id] = {"groups": set(), "channels": set()}

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
            "links": {"action": "delete", "duration": "1h", "warn": True, "delete": True, "enabled": False},
            "forward": {"action": "delete", "duration": "1h", "warn": True, "delete": True, "enabled": False}
        }

# ----------- Bot Handlers -----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    initialize_user_chats(user_id)
    
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
        # Add chat to user's list when bot is added to group/channel
        chat_id = str(update.message.chat.id)
        chat_type = "channel" if update.message.chat.type == "channel" else "group"
        initialize_user_chats(user_id)
        user_chats[user_id][f"{chat_type}s"].add(chat_id)
        initialize_group_settings(chat_id, chat_type)
        await show_help(update, context)

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🤖 *Bot Commands*:

*Group Admin Commands*:
/ban [time] - Ban user (reply to message)
/mute [time] - Mute user (reply to message)
/warn - Warn user (reply to message)
/unban - Unban user
/unmute - Unmute user
/settings - Configure settings
/allowlink [domain] - Allow domain
/blocklink [domain] - Block domain

Examples:
/ban 1h - Ban for 1 hour
/mute 2d - Mute for 2 days
"""
    if isinstance(update, Update):
        await update.message.reply_text(help_text, parse_mode="Markdown")
    else:
        await update.edit_message_text(help_text, parse_mode="Markdown")

async def group_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.message.chat
    group_id = str(chat.id)
    if chat.type == "channel":
        await show_channel_settings(update, group_id)
    else:
        await show_group_settings(update, group_id)

async def show_group_settings(update_or_query, group_id: str):
    initialize_group_settings(group_id)
    
    keyboard = [
        [InlineKeyboardButton("🔗 Link Settings", callback_data=f"link_settings_{group_id}")],
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

async def show_channel_settings(update_or_query, channel_id: str):
    initialize_group_settings(channel_id, "channel")
    settings = group_settings[channel_id]
    
    status = "✅ ON" if settings["remove_forward_tag"] else "❌ OFF"
    keyboard = [
        [InlineKeyboardButton(f"↩️ Remove Forward Tag: {status}", callback_data=f"toggle_forward_tag_{channel_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="your_channels")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "📢 *Channel Settings*\n\nConfigure forwarding behavior:"
    
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
        [InlineKeyboardButton(f"🔘 Enabled: {enabled}", callback_data=f"toggle_links_enabled_{group_id}")],
        [InlineKeyboardButton(f"⚡ Action: {action}", callback_data=f"cycle_link_action_{group_id}")],
        [InlineKeyboardButton(f"⏱ Duration: {duration}", callback_data=f"change_link_duration_{group_id}")],
        [InlineKeyboardButton(f"⚠️ Warn: {warn}", callback_data=f"toggle_link_warn_{group_id}")],
        [InlineKeyboardButton("✏️ Allowed Domains", callback_data=f"edit_domains_{group_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"group_{group_id}")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🔗 *Link Settings*\n\nConfigure how to handle links:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def show_user_groups(query):
    user_id = query.from_user.id
    initialize_user_chats(user_id)
    
    if not user_chats[user_id]["groups"]:
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📊 *Your Groups*\n\nYou haven't added me to any groups yet!",
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
            logger.warning(f"Couldn't fetch group {group_id}: {e}")
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="start")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "📊 *Your Groups*\n\nSelect a group to configure:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def show_user_channels(query):
    user_id = query.from_user.id
    initialize_user_chats(user_id)
    
    if not user_chats[user_id]["channels"]:
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📢 *Your Channels*\n\nYou haven't added me to any channels yet!",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return
    
    keyboard = []
    for channel_id in user_chats[user_id]["channels"]:
        try:
            chat = await query.bot.get_chat(int(channel_id))
            keyboard.append([InlineKeyboardButton(chat.title, callback_data=f"channel_{channel_id}")])
        except Exception as e:
            logger.warning(f"Couldn't fetch channel {channel_id}: {e}")
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="start")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "📢 *Your Channels*\n\nSelect a channel to configure:",
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
            await show_group_settings(query, group_id)
        elif data.startswith("channel_"):
            channel_id = data.split("_")[1]
            await show_channel_settings(query, channel_id)
        elif data.startswith("link_settings_"):
            group_id = data.split("_")[2]
            await show_link_settings(query, group_id)
        elif data.startswith("toggle_forward_tag_"):
            channel_id = data.split("_")[3]
            group_settings[channel_id]["remove_forward_tag"] = not group_settings[channel_id]["remove_forward_tag"]
            await show_channel_settings(query, channel_id)
        elif data.startswith("toggle_links_enabled_"):
            group_id = data.split("_")[3]
            action_settings[group_id]["links"]["enabled"] = not action_settings[group_id]["links"]["enabled"]
            await show_link_settings(query, group_id)
        elif data.startswith("cycle_link_action_"):
            group_id = data.split("_")[3]
            actions = ["delete", "mute", "ban"]
            current = action_settings[group_id]["links"]["action"]
            next_action = actions[(actions.index(current) + 1) % len(actions)]
            action_settings[group_id]["links"]["action"] = next_action
            await show_link_settings(query, group_id)
        elif data.startswith("change_link_duration_"):
            group_id = data.split("_")[3]
            durations = ["1h", "6h", "1d", "3d", "7d"]
            current = action_settings[group_id]["links"]["duration"]
            next_duration = durations[(durations.index(current) + 1) % len(durations)]
            action_settings[group_id]["links"]["duration"] = next_duration
            await show_link_settings(query, group_id)
        elif data.startswith("toggle_link_warn_"):
            group_id = data.split("_")[3]
            action_settings[group_id]["links"]["warn"] = not action_settings[group_id]["links"]["warn"]
            await show_link_settings(query, group_id)
        elif data == "back":
            await start(update, context)
    except Exception as e:
        logger.error(f"Error in button handler: {e}")
        await query.edit_message_text("❌ An error occurred. Please try again.")

async def message_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
        
    message = update.message
    chat_id = str(message.chat.id)
    chat_type = "channel" if message.chat.type == "channel" else "group"
    initialize_group_settings(chat_id, chat_type)
    
    # Channel specific handling
    if chat_type == "channel":
        if group_settings[chat_id]["remove_forward_tag"] and message.forward_from_chat:
            try:
                await message.edit_forward_sender_name(None)
            except Exception as e:
                logger.warning(f"Couldn't remove forward tag: {e}")
        return
    
    # Group handling
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
        logger.warning(f"Couldn't delete message: {e}")
    
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
            await message.reply_text(f"🔇 User muted for {format_duration(duration)}")
        elif action == "ban":
            until_date = datetime.now() + duration
            await context.bot.ban_chat_member(
                chat_id=int(chat_id),
                user_id=user_id,
                until_date=until_date
            )
            await message.reply_text(f"🚫 User banned for {format_duration(duration)}")
    except Exception as e:
        logger.error(f"Couldn't take action {action}: {e}")

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat.id)
    user_id = update.message.from_user.id
    initialize_group_settings(chat_id)
    
    if chat_id not in user_warnings:
        user_warnings[chat_id] = {}
    
    warnings = user_warnings[chat_id].get(user_id, 0) + 1
    user_warnings[chat_id][user_id] = warnings
    
    await update.message.reply_text(f"⚠️ Warning {warnings}/3 to {update.message.from_user.first_name}")
    
    if warnings >= 3:
        try:
            await context.bot.ban_chat_member(
                chat_id=int(chat_id),
                user_id=user_id,
                until_date=datetime.now() + timedelta(hours=1)
            )
            await update.message.reply_text("🚫 User banned (3 warnings)")
            user_warnings[chat_id][user_id] = 0
        except Exception as e:
            await update.message.reply_text(f"Failed to ban user: {e}")

# ---------------- RUN BOT ------------------

if __name__ == "__main__":
    TOKEN = "7735984673:AAGEhbsdIfO-j8B3DvBwBW9JSb9BcPd_J6o"
    app = ApplicationBuilder().token(TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", show_help))
    app.add_handler(CommandHandler("settings", group_settings_command))
    app.add_handler(MessageHandler(filters.ALL, message_filter))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot is running...")
    app.run_polling()
