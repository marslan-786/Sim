import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatPermissions,
    MessageEntity
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from datetime import datetime, timedelta
from typing import Dict, Set, List, Union

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# In-memory data stores
group_settings: Dict[int, dict] = {}
action_settings: Dict[int, dict] = {}
user_chats: Dict[int, Dict[str, Set[int]]] = {}  # groups and channels as sets of ints
user_warnings: Dict[int, Dict[int, int]] = {}  # chat_id -> {user_id: warnings_count}
admin_list: Dict[int, List[int]] = {}  # chat_id -> list of admin user ids


# Duration helpers
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
    minutes = (duration.seconds % 3600) // 60
    if minutes > 0:
        return f"{minutes} منٹ"
    return "چند سیکنڈ"

# Initialize group defaults
def initialize_group_settings(chat_id: int, chat_type: str = "group"):
    if chat_id not in group_settings:
        group_settings[chat_id] = {
            "block_links": False,
            "block_forwards": False,
            "remove_forward_tag": False,
            "block_mentions": False,
            "allowed_domains": set(),
            "chat_type": chat_type
        }
    if chat_id not in action_settings:
        action_settings[chat_id] = {
            "links": {"action": "delete", "duration": "1h", "warn": True, "delete": True, "enabled": False},
            "forward": {"action": "delete", "duration": "1h", "warn": True, "delete": True, "enabled": False},
            "mentions": {"action": "delete", "duration": "1h", "warn": True, "delete": True, "enabled": False}
        }
    if chat_id not in admin_list:
        admin_list[chat_id] = []
    if chat_id not in user_warnings:
        user_warnings[chat_id] = {}

# Track which groups/channels a user has started with the bot
def initialize_user_chats(user_id: int):
    if user_id not in user_chats:
        user_chats[user_id] = {"groups": set(), "channels": set()}
        
        
# /start handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    initialize_user_chats(user_id)

    if update.message.chat.type == "private":
        keyboard = [
            [InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
            [InlineKeyboardButton("📊 My Groups", callback_data="your_groups")],
            [InlineKeyboardButton("📢 My Channels", callback_data="your_channels")],
            [InlineKeyboardButton("❓ Help", callback_data="help_command")]
        ]
        await update.message.reply_text(
            "👋 Welcome to Group Management Bot!\n\n"
            "🔹 Add me to your groups/channels\n"
            "🔹 Configure settings\n"
            "🔹 Advanced admin tools",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        cid = update.message.chat.id
        ctype = "channel" if update.message.chat.type == "channel" else "group"
        initialize_user_chats(user_id)
        user_chats[user_id][f"{ctype}s"].add(cid)
        initialize_group_settings(cid, ctype)
        await show_help(update, context)

# /help handler
async def show_help(update_or_query: Union[Update, CallbackQueryHandler], context=None):
    text = """
🤖 *Bot Commands*:

*Admin Commands:*
/ban [duration] – Ban user (reply)
/mute [duration] – Mute user (reply)
/warn – Warn user (reply)
/unban – Unban user
/unmute – Unmute user
/settings – Configure settings
/allowlink [domain] – Allow domain
/blocklink [domain] – Block domain

Examples:
/ban 1h – Ban for 1 hour
/mute 2d – Mute for 2 days
"""
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(text, parse_mode="Markdown")
    else:
        await update_or_query.edit_message_text(text, parse_mode="Markdown")


# Show user's groups as inline buttons
async def show_user_groups(query):
    user_id = query.from_user.id
    groups = user_chats.get(user_id, {}).get("groups", set())
    if not groups:
        await query.edit_message_text("😕 آپ نے ابھی کسی گروپ میں اس بوٹ کو شامل نہیں کیا۔")
        return

    kb = []
    for gid in groups:
        kb.append([InlineKeyboardButton(f"Group: {gid}", callback_data=f"group_{gid}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="start")])
    await query.edit_message_text("📊 آپ کے گروپس:", reply_markup=InlineKeyboardMarkup(kb))

# Show user's channels as inline buttons
async def show_user_channels(query):
    user_id = query.from_user.id
    channels = user_chats.get(user_id, {}).get("channels", set())
    if not channels:
        await query.edit_message_text("😕 آپ نے ابھی کسی چینل میں اس بوٹ کو شامل نہیں کیا۔")
        return

    kb = []
    for cid in channels:
        kb.append([InlineKeyboardButton(f"Channel: {cid}", callback_data=f"group_{cid}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="start")])
    await query.edit_message_text("📢 آپ کے چینلز:", reply_markup=InlineKeyboardMarkup(kb))
    
    
    
# Show settings menu for a group
async def show_group_settings(update_or_query: Union[Update, CallbackQueryHandler], gid: int):
    initialize_group_settings(gid)
    kb = [
        [InlineKeyboardButton("🔗 Link Settings", callback_data=f"link_settings_{gid}")],
        [InlineKeyboardButton("↩️ Forward Settings", callback_data=f"forward_settings_{gid}")],
        [InlineKeyboardButton("🗣 Mention Settings", callback_data=f"mention_settings_{gid}")],
        [InlineKeyboardButton("🔙 Back", callback_data="your_groups")]  # Back to user groups list
    ]
    text = f"⚙️ *Settings for* `{gid}`\nSelect category:"
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    else:
        await update_or_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# Show link settings submenu
async def show_link_settings(query: CallbackQueryHandler, gid: int):
    s = action_settings[gid]["links"]
    kb = [
        [InlineKeyboardButton(f"Enabled: {'✅' if s['enabled'] else '❌'}", callback_data=f"toggle_links_enabled_{gid}")],
        [InlineKeyboardButton(f"Action: {s['action']}", callback_data=f"cycle_link_action_{gid}")],
        [InlineKeyboardButton(f"Duration: {s['duration']}", callback_data=f"change_link_duration_{gid}")],
        [InlineKeyboardButton(f"Warn: {'✅' if s['warn'] else '❌'}", callback_data=f"toggle_link_warn_{gid}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"group_settings_back_{gid}")]  # Back to group main settings
    ]
    await query.edit_message_text("🔗 *Link Settings*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# Show forward settings submenu
async def show_forward_settings(query: CallbackQueryHandler, gid: int):
    s = action_settings[gid]["forward"]
    kb = [
        [InlineKeyboardButton(f"Enabled: {'✅' if s['enabled'] else '❌'}", callback_data=f"toggle_forward_enabled_{gid}")],
        [InlineKeyboardButton(f"Action: {s['action']}", callback_data=f"cycle_forward_action_{gid}")],
        [InlineKeyboardButton(f"Duration: {s['duration']}", callback_data=f"change_forward_duration_{gid}")],
        [InlineKeyboardButton(f"Warn: {'✅' if s['warn'] else '❌'}", callback_data=f"toggle_forward_warn_{gid}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"group_settings_back_{gid}")]  # Back to group main settings
    ]
    await query.edit_message_text("↩️ *Forward Settings*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# Show mention settings submenu
async def show_mention_settings(query: CallbackQueryHandler, gid: int):
    s = action_settings[gid]["mentions"]
    kb = [
        [InlineKeyboardButton(f"Enabled: {'✅' if s['enabled'] else '❌'}", callback_data=f"toggle_mention_enabled_{gid}")],
        [InlineKeyboardButton(f"Action: {s['action']}", callback_data=f"cycle_mention_action_{gid}")],
        [InlineKeyboardButton(f"Duration: {s['duration']}", callback_data=f"change_mention_duration_{gid}")],
        [InlineKeyboardButton(f"Warn: {'✅' if s['warn'] else '❌'}", callback_data=f"toggle_mention_warn_{gid}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"group_settings_back_{gid}")]  # Back to group main settings
    ]
    await query.edit_message_text("🗣 *Mention Settings*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    
    
# Main button handler for all inline buttons
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id
    await q.answer()

    try:
        if data == "start":
            return await start(update, context)
        if data == "your_groups":
            return await show_user_groups(q)
        if data == "your_channels":
            return await show_user_channels(q)
        if data == "help_command":
            return await show_help(q, context)

        if data.startswith("group_"):
            gid = int(data.split("_",1)[1])
            if await is_admin(gid, uid, context):
                return await show_group_settings(q, gid)
            return await q.answer("⚠️ صرف ایڈمنز کے لیے!", show_alert=True)

        # Back button from submenus to group settings
        if data.startswith("group_settings_back_"):
            gid = int(data.rsplit("_",1)[1])
            if await is_admin(gid, uid, context):
                return await show_group_settings(q, gid)
            return await q.answer("⚠️ صرف ایڈمنز کے لیے!", show_alert=True)

        # Link toggles
        if data.startswith("toggle_links_enabled_"):
            gid = int(data.rsplit("_",1)[1])
            action_settings[gid]["links"]["enabled"] = not action_settings[gid]["links"]["enabled"]
            return await show_link_settings(q, gid)
        if data.startswith("cycle_link_action_"):
            gid = int(data.rsplit("_",1)[1])
            opts = ["delete", "mute", "ban"]
            cur = action_settings[gid]["links"]["action"]
            action_settings[gid]["links"]["action"] = opts[(opts.index(cur)+1)%3]
            return await show_link_settings(q, gid)
        if data.startswith("change_link_duration_"):
            gid = int(data.rsplit("_",1)[1])
            opts = ["30m","1h","6h","1d","3d","7d"]
            cur = action_settings[gid]["links"]["duration"]
            action_settings[gid]["links"]["duration"] = opts[(opts.index(cur)+1)%len(opts)]
            return await show_link_settings(q, gid)
        if data.startswith("toggle_link_warn_"):
            gid = int(data.rsplit("_",1)[1])
            action_settings[gid]["links"]["warn"] = not action_settings[gid]["links"]["warn"]
            return await show_link_settings(q, gid)

        # Forward toggles
        if data.startswith("toggle_forward_enabled_"):
            gid = int(data.rsplit("_",1)[1])
            action_settings[gid]["forward"]["enabled"] = not action_settings[gid]["forward"]["enabled"]
            return await show_forward_settings(q, gid)
        if data.startswith("cycle_forward_action_"):
            gid = int(data.rsplit("_",1)[1])
            opts = ["delete", "mute", "ban"]
            cur = action_settings[gid]["forward"]["action"]
            action_settings[gid]["forward"]["action"] = opts[(opts.index(cur)+1)%3]
            return await show_forward_settings(q, gid)
        if data.startswith("change_forward_duration_"):
            gid = int(data.rsplit("_",1)[1])
            opts = ["30m","1h","6h","1d","3d","7d"]
            cur = action_settings[gid]["forward"]["duration"]
            action_settings[gid]["forward"]["duration"] = opts[(opts.index(cur)+1)%len(opts)]
            return await show_forward_settings(q, gid)
        if data.startswith("toggle_forward_warn_"):
            gid = int(data.rsplit("_",1)[1])
            action_settings[gid]["forward"]["warn"] = not action_settings[gid]["forward"]["warn"]
            return await show_forward_settings(q, gid)

        # Mention toggles
        if data.startswith("toggle_mention_enabled_"):
            gid = int(data.rsplit("_",1)[1])
            action_settings[gid]["mentions"]["enabled"] = not action_settings[gid]["mentions"]["enabled"]
            return await show_mention_settings(q, gid)
        if data.startswith("cycle_mention_action_"):
            gid = int(data.rsplit("_",1)[1])
            opts = ["delete", "mute", "ban"]
            cur = action_settings[gid]["mentions"]["action"]
            action_settings[gid]["mentions"]["action"] = opts[(opts.index(cur)+1)%3]
            return await show_mention_settings(q, gid)
        if data.startswith("change_mention_duration_"):
            gid = int(data.rsplit("_",1)[1])
            opts = ["30m","1h","6h","1d","3d","7d"]
            cur = action_settings[gid]["mentions"]["duration"]
            action_settings[gid]["mentions"]["duration"] = opts[(opts.index(cur)+1)%len(opts)]
            return await show_mention_settings(q, gid)
        if data.startswith("toggle_mention_warn_"):
            gid = int(data.rsplit("_",1)[1])
            action_settings[gid]["mentions"]["warn"] = not action_settings[gid]["mentions"]["warn"]
            return await show_mention_settings(q, gid)

        await q.answer("Unknown button!", show_alert=True)
    except Exception as e:
        logger.error(f"Callback error: {e}")
        await q.edit_message_text("❌ کچھ غلط ہوگیا، دوبارہ کوشش کریں۔")
        
        
# Check admin rights
async def is_admin(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        return any(a.user.id == user_id for a in admins)
    except Exception as e:
        logger.error(f"Admin check failed: {e}")
        return False


# Main
if __name__ == "__main__":
    TOKEN = "7735984673:AAGEhbsdIfO-j8B3DvBwBW9JSb9BcPd_J6o"  # یہاں اپنا بوٹ ٹوکن لگائیں
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", show_help))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot is running...")
    app.run_polling()
