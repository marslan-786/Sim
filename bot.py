import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Set, List, Union
from telegram.ext import ContextTypes

from telegram import (
    Update,
    CallbackQuery,
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

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Memory data stores
channel_settings = {}  # Structure: {channel_id: {"remove_forward_tag": True/False}}
channel_forward_settings = {}  # Example: {123456789: {"remove_forward_tag": True}}
user_state = {}  # user_id: {"state": ..., "gid": ...}
user_custom_add: Dict[int, int] = {}  # user_id -> group_id
group_settings: Dict[int, dict] = {}
action_settings: Dict[int, dict] = {}
user_chats: Dict[int, Dict[str, Set[int]]] = {}  # store groups/channels in sets
user_warnings: Dict[int, Dict[int, int]] = {}  # chat_id -> {user_id: warning_count}
admin_list: Dict[int, List[int]] = {}  # chat_id -> list of admins

# Duration parser helper
def parse_duration(duration_str: str) -> timedelta:
    """
    Parse duration string to timedelta.
    Supported formats: 30m, 1h, 6h, 1d, 3d, 7d
    or in words: "30 minutes", "1 hour", "3 days", etc.
    Defaults to 1 hour if invalid or missing.
    """
    if not duration_str:
        return timedelta(hours=1)

    duration_str = duration_str.strip().lower()
    match = re.match(r"(\d+)\s*(m|min|minute|minutes|h|hr|hour|hours|d|day|days)?", duration_str)
    if not match:
        return timedelta(hours=1)

    value = int(match.group(1))
    unit = match.group(2) or "h"

    if unit.startswith("m"):
        return timedelta(minutes=value)
    elif unit.startswith("h"):
        return timedelta(hours=value)
    elif unit.startswith("d"):
        return timedelta(days=value)
    else:
        return timedelta(hours=1)

# Format duration into human-readable string
def format_duration(duration: timedelta) -> str:
    days = duration.days
    seconds = duration.seconds
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60

    if days > 0:
        return f"{days} day(s)"
    elif hours > 0:
        return f"{hours} hour(s)"
    elif minutes > 0:
        return f"{minutes} minute(s)"
    else:
        return "a few seconds"

# Default group settings
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
            "links": {"action": "off", "duration": "1h", "warn": True, "delete": True, "enabled": False},
            "forward": {"action": "off", "duration": "1h", "warn": True, "delete": True, "enabled": False},
            "mentions": {"action": "off", "duration": "1h", "warn": True, "delete": True, "enabled": False},
            "custom": {
                "enabled": False,
                "action": "off",  # 'off', 'mute', 'ban', 'warn'
                "warn_count": 1,
                "duration": "1h",
                "messages": []
            }
        }
    if chat_id not in admin_list:
        admin_list[chat_id] = []
    if chat_id not in user_warnings:
        user_warnings[chat_id] = {}

# Track user's groups/channels
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    initialize_user_chats(user_id)

    message = update.message or update.callback_query.message
    if not message:
        return

    keyboard = [
        [InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
        [InlineKeyboardButton("📊 My Groups", callback_data="your_groups")],
        [InlineKeyboardButton("⚙️ Channel Settings", callback_data="channel_settings")],
        [InlineKeyboardButton("❓ Help", callback_data="help_command")]
    ]

    # Remove this condition to show menu everywhere
    await message.reply_text(
        "👋 Welcome to Kami_Broken\n\n"
        "Group Management Bot!\n"
        "🔹 Add to your Groups/Channels\n"
        "🔹 Configure settings\n"
        "🔹 Admin Tools",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# /help handler
async def show_help(update_or_query: Union[Update, CallbackQueryHandler], context=None):
    text = """
🤖 *Bot Commands*:

*Admin Commands:*
/ban [duration] – Ban a user (use as reply)
/mute [duration] – Mute a user (use as reply)
/unban – Unban a user
/unmute – Unmute a user
/settings – Configure group settings

Examples:
/ban 1h – Ban for 1 hour
/mute 2d – Mute for 2 days
"""
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(text, parse_mode="Markdown")
    else:
        await update_or_query.edit_message_text(text, parse_mode="Markdown")


# Show user's groups as buttons
async def show_user_groups(query):
    user_id = query.from_user.id
    groups = user_chats.get(user_id, {}).get("groups", set())
    if not groups:
        await query.edit_message_text("😕 You haven't added this bot to any group yet. Please Again /start")
        return

    kb = []
    for gid in groups:
        kb.append([InlineKeyboardButton(f"Group: {gid}", callback_data=f"group_{gid}")])
    kb.append([InlineKeyboardButton("🏠 Menu", callback_data="force_start")])
    await query.edit_message_text("📊 Your Groups:", reply_markup=InlineKeyboardMarkup(kb))

# Show user's channels as buttons
async def toggle_forward_removal(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    user_id = query.from_user.id

    # اگر یوزر کا سیٹنگ نہ ہو تو ڈیفالٹ سیٹ کریں
    if user_id not in channel_forward_settings:
        channel_forward_settings[user_id] = {"remove_forward_tag": False}

    # موجودہ اسٹیٹ حاصل کریں
    current_state = channel_forward_settings[user_id]["remove_forward_tag"]

    # اسٹیٹ کو ٹوگل کریں
    channel_forward_settings[user_id]["remove_forward_tag"] = not current_state

    # نیا اسٹیٹ حاصل کریں
    new_state = channel_forward_settings[user_id]["remove_forward_tag"]
    status = "✅ ON" if new_state else "❌ OFF"
    toggle_text = f"🔁 Forward Tag Removal: {status}"

    keyboard = [
        [InlineKeyboardButton(toggle_text, callback_data="toggle_forward_removal")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="force_start")]
    ]

    # میسج کو اپڈیٹ کریں
    await query.edit_message_text(
        text="📢 Channel Settings:\n\nChoose what to do with forwarded messages:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    # کال بیک کو اَکناولج کریں تاکہ "loading..." ریمو ہو جائے
    await query.answer()
    
async def global_channel_settings(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    user_id = query.from_user.id

    if user_id not in channel_forward_settings:
        channel_forward_settings[user_id] = {"remove_forward_tag": False}

    current_state = channel_forward_settings[user_id]["remove_forward_tag"]
    status = "✅ ON" if current_state else "❌ OFF"
    toggle_text = f"🔁 Forward Tag Removal: {status}"

    keyboard = [
        [InlineKeyboardButton(toggle_text, callback_data="toggle_forward_removal")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="force_start")]
    ]

    await query.edit_message_text(
        text="📢 Channel Settings:\n\nChoose what to do with forwarded messages:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Show group settings menu
async def show_group_settings(update_or_query: Union[Update, CallbackQueryHandler], gid: int):
    initialize_group_settings(gid)
    kb = [
        [InlineKeyboardButton("🔗 Link Settings", callback_data=f"link_settings_{gid}")],
        [InlineKeyboardButton("↩️ Forward Settings", callback_data=f"forward_settings_{gid}")],
        [InlineKeyboardButton("🗣 Mention Settings", callback_data=f"mention_settings_{gid}")],
        [InlineKeyboardButton("📝 Custom Message Filter", callback_data=f"custom_settings_{gid}")],
        [InlineKeyboardButton("🔙 Back", callback_data="your_groups")]
    ]
    text = f"⚙️ *Settings for* `{gid}`\nChoose a category:"
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    else:
        await update_or_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


# Show Link Settings submenu
async def show_link_settings(query, gid):
    s = action_settings[gid]["links"]
    buttons = []

    buttons.append([InlineKeyboardButton(
        f"✅ Link Filtering: {'On' if s['enabled'] else 'Off'}",
        callback_data=f"toggle_links_enabled_{gid}"
    )])

    if s["enabled"]:
        current_action = s.get('action', 'off')

        buttons.append([InlineKeyboardButton(
            f"🎯 Action: {current_action.capitalize()}",
            callback_data=f"cycle_link_action_{gid}"
        )])

        if current_action == "warn":
            warn_count = s.get('warn_count', 1)
            buttons.append([InlineKeyboardButton(
                f"⚠️ Warning Count: {warn_count}",
                callback_data=f"cycle_link_warn_count_{gid}"
            )])

        buttons.append([InlineKeyboardButton(
            f"⏰ Duration: {s.get('duration', '30m')}",
            callback_data=f"change_link_duration_{gid}"
        )])

    buttons.append([InlineKeyboardButton("📋 Menu", callback_data="force_start")])

    await query.edit_message_text(
        text="🔗 *Link Settings*",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )


# Show Forward Settings submenu
async def show_forward_settings(query, gid):
    s = action_settings[gid]["forward"]
    buttons = []

    buttons.append([InlineKeyboardButton(
        f"✅ Forward Filtering: {'On' if s['enabled'] else 'Off'}",
        callback_data=f"toggle_forward_enabled_{gid}"
    )])

    if s["enabled"]:
        current_action = s.get('action', 'off')

        buttons.append([InlineKeyboardButton(
            f"🎯 Action: {current_action.capitalize()}",
            callback_data=f"cycle_forward_action_{gid}"
        )])

        if current_action == "warn":
            warn_count = s.get('warn_count', 1)
            buttons.append([InlineKeyboardButton(
                f"⚠️ Warning Count: {warn_count}",
                callback_data=f"cycle_forward_warn_count_{gid}"
            )])

        buttons.append([InlineKeyboardButton(
            f"⏰ Duration: {s.get('duration', '30m')}",
            callback_data=f"change_forward_duration_{gid}"
        )])

    buttons.append([InlineKeyboardButton("📋 Menu", callback_data="force_start")])

    await query.edit_message_text(
        text="📤 *Forward Settings*",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )


# Show Mention Settings submenu
async def show_mention_settings(query, gid):
    s = action_settings[gid]["mentions"]
    buttons = []

    buttons.append([InlineKeyboardButton(
        f"✅ Mention Filtering: {'On' if s['enabled'] else 'Off'}",
        callback_data=f"toggle_mention_enabled_{gid}"
    )])

    if s["enabled"]:
        current_action = s.get('action', 'off')

        buttons.append([InlineKeyboardButton(
            f"🎯 Action: {current_action.capitalize()}",
            callback_data=f"cycle_mention_action_{gid}"
        )])

        if current_action == "warn":
            warn_count = s.get('warn_count', 1)
            buttons.append([InlineKeyboardButton(
                f"⚠️ Warning Count: {warn_count}",
                callback_data=f"cycle_mention_warn_count_{gid}"
            )])

        buttons.append([InlineKeyboardButton(
            f"⏰ Duration: {s.get('duration', '30m')}",
            callback_data=f"change_mention_duration_{gid}"
        )])

    buttons.append([InlineKeyboardButton("📋 Menu", callback_data="force_start")])

    await query.edit_message_text(
        text="👥 *Mention Settings*",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )


# 📝 Show Custom Message Filter Settings submenu
async def show_custom_settings(query, gid):
    s = action_settings[gid]["custom"]
    buttons = []

    buttons.append([InlineKeyboardButton(
        f"✅ Filtering: {'On' if s['enabled'] else 'Off'}",
        callback_data=f"toggle_custom_enabled_{gid}"
    )])

    if s["enabled"]:
        current_action = s.get('action', 'off')

        buttons.append([InlineKeyboardButton(
            f"🎯 Action: {current_action.capitalize()}",
            callback_data=f"cycle_custom_action_{gid}"
        )])

        if current_action == "warn":
            warn_count = s.get('warn_count', 1)
            buttons.append([InlineKeyboardButton(
                f"⚠️ Warning Count: {warn_count}",
                callback_data=f"cycle_custom_warn_count_{gid}"
            )])

        buttons.append([InlineKeyboardButton(
            f"⏰ Duration: {s.get('duration', '30m')}",
            callback_data=f"change_custom_duration_{gid}"
        )])

        buttons.append([InlineKeyboardButton(
            "➕ Add Custom Message",
            callback_data=f"add_custom_message_{gid}"
        )])

    buttons.append([InlineKeyboardButton("📋 Menu", callback_data="force_start")])

    await query.edit_message_text(
        text="📝 *Custom Message Settings*",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )
    
# Handle messages to apply filters like custom, links, forwards, mentions
async def message_filter_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = message.chat.id
    user_id = message.from_user.id

    if chat_id not in group_settings or user_id == context.bot.id:
        return

    text = message.text or message.caption or ""
    is_forwarded = message.forward_from or message.forward_from_chat
    has_links = bool(re.search(r"https?://|t\.me|telegram\.me|www\.", text))
    has_mentions = any(e.type in [MessageEntity.MENTION, MessageEntity.TEXT_MENTION] for e in message.entities or [])

    actions = action_settings.get(chat_id, {})
    settings = group_settings.get(chat_id, {})

    try:
        # ✅ Link filter
        if settings.get("block_links") and actions.get("links", {}).get("enabled") and has_links:
            return await apply_action("links", chat_id, user_id, message, context)

        # ✅ Forward filter
        elif settings.get("block_forwards") and actions.get("forward", {}).get("enabled") and is_forwarded:
            return await apply_action("forward", chat_id, user_id, message, context)

        # ✅ Mention filter
        elif settings.get("block_mentions") and actions.get("mentions", {}).get("enabled") and has_mentions:
            return await apply_action("mentions", chat_id, user_id, message, context)

        # ✅ Custom message filter
        elif actions.get("custom", {}).get("enabled") and "custom_messages" in group_settings[chat_id]:
            for word in group_settings[chat_id]["custom_messages"]:
                if word.lower() in text.lower():
                    return await apply_action("custom", chat_id, user_id, message, context)

    except Exception as e:
        logger.error(f"Filter Handler Error: {e}")


# Apply mute/ban/warn action
async def apply_action(filter_type: str, chat_id: int, user_id: int, message, context):
    s = action_settings[chat_id][filter_type]
    action = s["action"]
    duration = parse_duration(s["duration"])
    username = message.from_user.mention_html()
    reason_map = {
        "links": "Link Sending",
        "forward": "Forwarded Messages",
        "mentions": "Mentions",
        "custom": "Custom Message"
    }
    reason = reason_map.get(filter_type, "Unknown Reason")

    # Delete the triggering message
    await message.delete()

    button_list = []

    if action == "mute":
        until_date = datetime.utcnow() + duration
        permissions = ChatPermissions(can_send_messages=False)
        await context.bot.restrict_chat_member(chat_id, user_id, permissions=permissions, until_date=until_date)

        button_list = [[InlineKeyboardButton("🔓 Unmute", callback_data=f"unmute_{chat_id}_{user_id}")]]
        action_text = f"🔇 User muted for {format_duration(duration)}."

    elif action == "ban":
        until_date = datetime.utcnow() + duration
        await context.bot.ban_chat_member(chat_id, user_id, until_date=until_date)

        button_list = [[InlineKeyboardButton("♻️ Unban", callback_data=f"unban_{chat_id}_{user_id}")]]
        action_text = f"🚫 User banned for {format_duration(duration)}."

    elif action == "warn":
        user_warnings.setdefault(chat_id, {})
        user_warnings[chat_id][user_id] = user_warnings[chat_id].get(user_id, 0) + 1
        warn_count = user_warnings[chat_id][user_id]
        max_warn = s.get("warn_count", 3)

        # Buttons to modify warnings
        button_list = [
            [
                InlineKeyboardButton("➕ Increase Warning", callback_data=f"warnadd_{chat_id}_{user_id}"),
                InlineKeyboardButton("➖ Decrease Warning", callback_data=f"warndec_{chat_id}_{user_id}")
            ],
            [InlineKeyboardButton("🗑️ Reset Warnings", callback_data=f"warnreset_{chat_id}_{user_id}")]
        ]
        action_text = f"⚠️ Warning {warn_count}/{max_warn} given."

        if warn_count >= max_warn:
            post_action = s.get("post_warn_action", "mute")
            until_date = datetime.utcnow() + duration

            # Delete old warning message
            try:
                await message.delete()
            except:
                pass

            # Apply mute/ban
            if post_action == "ban":
                await context.bot.ban_chat_member(chat_id, user_id, until_date=until_date)
                action_text = f"🚫 User automatically banned after {warn_count} warnings."
                button_list = [[InlineKeyboardButton("♻️ Unban", callback_data=f"unban_{chat_id}_{user_id}")]]
            else:
                permissions = ChatPermissions(can_send_messages=False)
                await context.bot.restrict_chat_member(chat_id, user_id, permissions=permissions, until_date=until_date)
                action_text = f"🔇 User automatically muted after {warn_count} warnings."
                button_list = [[InlineKeyboardButton("🔓 Unmute", callback_data=f"unmute_{chat_id}_{user_id}")]]

            # Reset warnings
            user_warnings[chat_id][user_id] = 0

    msg = (
        f"<b>👤 User:</b> {username}\n"
        f"<b>🎯 Action:</b> {action_text}\n"
        f"<b>📌 Reason:</b> {reason}"
    )
    reply_markup = InlineKeyboardMarkup(button_list) if button_list else None
    await message.chat.send_message(msg, reply_markup=reply_markup, parse_mode="HTML")

# Handle incoming custom message input from user
async def custom_message_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    if user_id not in user_state:
        return

    state_info = user_state[user_id]
    if state_info["state"] != "awaiting_custom_message":
        return

    gid = state_info["gid"]
    initialize_group_settings(gid)

    if "custom_messages" not in group_settings[gid]:
        group_settings[gid]["custom_messages"] = set()

    words = text.split()
    for word in words:
        group_settings[gid]["custom_messages"].add(word.lower())

    del user_state[user_id]

    await update.message.reply_text("✅ Your custom words have been saved!")
    await start(update, context)

async def message_filter_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user_id = message.from_user.id
    chat_id = message.chat_id

    # اگر میسج فارورڈ کیا گیا ہو اور یوزر نے ریموو والا ٹوگل آن کیا ہو
    if message.forward_from_chat and channel_forward_settings.get(user_id, {}).get("remove_forward_tag", False):
        try:
            # فارورڈ میسج کو ڈیلیٹ کریں
            await message.delete()

            # اور کاپی کر کے دوبارہ پوسٹ کریں - فارورڈ ٹیگ ہٹ جائے گا
            await context.bot.copy_message(
                chat_id=chat_id,
                from_chat_id=message.forward_from_chat.id,
                message_id=message.forward_from_message_id
            )
        except Exception as e:
            logger.warning(f"Failed to remove forward tag: {e}")

# Handle all inline button interactions
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id
    await q.answer()

    try:
        if data == "force_start":
            await q.message.delete()
            await start(update, context)
            return

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
            return await q.answer("⚠️ Admins only!", show_alert=True)

        if data.startswith("group_settings_"):
            gid = int(data.split("_",2)[2])
            if await is_admin(gid, uid, context):
                return await show_group_settings(q, gid)
            return await q.answer("⚠️ Admins only!", show_alert=True)

        if data.startswith("link_settings_"):
            gid = int(data.rsplit("_",1)[1])
            return await show_link_settings(q, gid)

        if data.startswith("forward_settings_"):
            gid = int(data.rsplit("_",1)[1])
            return await show_forward_settings(q, gid)

        if data.startswith("mention_settings_"):
            gid = int(data.rsplit("_",1)[1])
            return await show_mention_settings(q, gid)

        if data.startswith("toggle_links_enabled_"):
            gid = int(data.rsplit("_", 1)[1])
            initialize_group_settings(gid)
            s = action_settings[gid]["links"]
            s["enabled"] = not s["enabled"]
            group_settings[gid]["block_links"] = s["enabled"]
            if not s["enabled"]:
                s["action"] = "off"
            return await show_link_settings(q, gid)

        if data.startswith("cycle_link_action_"):
            gid = int(data.rsplit("_",1)[1])
            s = action_settings[gid]["links"]
            options = ['off', 'mute', 'ban', 'warn']
            s['action'] = options[(options.index(s.get('action', 'off')) + 1) % len(options)]
            return await show_link_settings(q, gid)

        if data.startswith("cycle_link_warn_count_"):
            gid = int(data.rsplit("_",1)[1])
            s = action_settings[gid]["links"]
            count = s.get('warn_count', 1)
            count = 1 if count >= 3 else count + 1
            s['warn_count'] = count
            return await show_link_settings(q, gid)

        if data.startswith("change_link_duration_"):
            gid = int(data.rsplit("_",1)[1])
            opts = ["30m","1h","6h","1d","3d","7d"]
            cur = action_settings[gid]["links"]["duration"]
            action_settings[gid]["links"]["duration"] = opts[(opts.index(cur)+1)%len(opts)]
            return await show_link_settings(q, gid)

        # Forward filter settings
        if data.startswith("toggle_forward_enabled_"):
            gid = int(data.rsplit("_",1)[1])
            initialize_group_settings(gid)
            s = action_settings[gid]["forward"]
            s['enabled'] = not s['enabled']
            group_settings[gid]["block_forwards"] = s["enabled"]
            if not s["enabled"]:
                s["action"] = "off"
            return await show_forward_settings(q, gid)

        if data.startswith("cycle_forward_action_"):
            gid = int(data.rsplit("_",1)[1])
            s = action_settings[gid]["forward"]
            options = ['off', 'mute', 'ban', 'warn']
            s['action'] = options[(options.index(s.get('action', 'off')) + 1) % len(options)]
            return await show_forward_settings(q, gid)

        if data.startswith("cycle_forward_warn_count_"):
            gid = int(data.rsplit("_",1)[1])
            s = action_settings[gid]["forward"]
            count = s.get('warn_count', 1)
            count = 1 if count >= 3 else count + 1
            s['warn_count'] = count
            return await show_forward_settings(q, gid)

        if data.startswith("change_forward_duration_"):
            gid = int(data.rsplit("_",1)[1])
            opts = ["30m","1h","6h","1d","3d","7d"]
            cur = action_settings[gid]["forward"]["duration"]
            action_settings[gid]["forward"]["duration"] = opts[(opts.index(cur)+1)%len(opts)]
            return await show_forward_settings(q, gid)

        # Mention settings
        if data.startswith("toggle_mention_enabled_"):
            gid = int(data.rsplit("_",1)[1])
            initialize_group_settings(gid)
            s = action_settings[gid]["mentions"]
            s['enabled'] = not s['enabled']
            group_settings[gid]["block_mentions"] = s["enabled"]
            if not s["enabled"]:
                s["action"] = "off"
            return await show_mention_settings(q, gid)

        if data.startswith("cycle_mention_action_"):
            gid = int(data.rsplit("_",1)[1])
            s = action_settings[gid]["mentions"]
            options = ['off', 'mute', 'ban', 'warn']
            s['action'] = options[(options.index(s.get('action', 'off')) + 1) % len(options)]
            return await show_mention_settings(q, gid)

        if data.startswith("cycle_mention_warn_count_"):
            gid = int(data.rsplit("_",1)[1])
            s = action_settings[gid]["mentions"]
            count = s.get('warn_count', 1)
            count = 1 if count >= 3 else count + 1
            s['warn_count'] = count
            return await show_mention_settings(q, gid)

        if data.startswith("change_mention_duration_"):
            gid = int(data.rsplit("_",1)[1])
            opts = ["30m","1h","6h","1d","3d","7d"]
            cur = action_settings[gid]["mentions"]["duration"]
            action_settings[gid]["mentions"]["duration"] = opts[(opts.index(cur)+1)%len(opts)]
            return await show_mention_settings(q, gid)
            
        # --- Unmute button ---
        if data.startswith("unmute_"):
            _, gid, uid = data.split("_")
            gid, uid = int(gid), int(uid)
            
            if not await is_admin(gid, q.from_user.id, context):
               return await q.answer("⚠️ Only admins can perform this action.", show_alert=True)
            try:
                permissions = ChatPermissions(
                    can_send_messages=True,
                )
                await context.bot.restrict_chat_member(gid, uid, permissions=permissions)
                await q.edit_message_text("✅ User has been unmuted.")
            except Exception as e:
                logger.error(f"Unmute error: {e}")
                await q.answer("❌ Failed to unmute.", show_alert=True)
            return

        # --- Unban button ---
        if data.startswith("unban_"):
            _, gid, uid = data.split("_")
            gid, uid = int(gid), int(uid)
            if not await is_admin(gid, q.from_user.id, context):
                return await q.answer("⚠️ Only admins can perform this action.", show_alert=True)
            try:
                await context.bot.unban_chat_member(gid, uid)
                await q.edit_message_text("✅ User has been unbanned.")
            except Exception as e:
                logger.error(f"Unban error: {e}")
                await q.answer("❌ Failed to unban.", show_alert=True)
            return

        # --- Increase Warning ---
        if data.startswith("warnadd_"):
            _, gid, uid = data.split("_")
            gid, uid = int(gid), int(uid)
            user_warnings.setdefault(gid, {})
            user_warnings[gid][uid] = user_warnings[gid].get(uid, 0) + 1
            warn_count = user_warnings[gid][uid]
            await q.answer(f"✅ Warning increased to {warn_count}.", show_alert=True)
            return

        # --- Decrease Warning ---
        if data.startswith("warndec_"):
            _, gid, uid = data.split("_")
            gid, uid = int(gid), int(uid)
            user_warnings.setdefault(gid, {})
            current = user_warnings[gid].get(uid, 0)
            if current > 0:
                user_warnings[gid][uid] = current - 1
            await q.answer(f"✅ Warning decreased to {user_warnings[gid][uid]}.", show_alert=True)
            return

        # --- Reset Warnings ---
        if data.startswith("warnreset_"):
            _, gid, uid = data.split("_")
            gid, uid = int(gid), int(uid)
            user_warnings.setdefault(gid, {})
            user_warnings[gid][uid] = 0
            await q.answer("✅ Warnings have been reset.", show_alert=True)
            return

        # Custom message filter settings
        if data.startswith("custom_settings_"):
            gid = int(data.rsplit("_", 1)[1])
            return await show_custom_settings(q, gid)

        if data.startswith("toggle_custom_enabled_"):
            gid = int(data.rsplit("_", 1)[1])
            initialize_group_settings(gid)
            s = action_settings[gid]["custom"]
            s["enabled"] = not s["enabled"]
            return await show_custom_settings(q, gid)

        if data.startswith("cycle_custom_action_"):
            gid = int(data.rsplit("_", 1)[1])
            s = action_settings[gid]["custom"]
            options = ['off', 'mute', 'ban', 'warn']
            s["action"] = options[(options.index(s.get("action", "off")) + 1) % len(options)]
            return await show_custom_settings(q, gid)

        if data.startswith("cycle_custom_warn_count_"):
            gid = int(data.rsplit("_", 1)[1])
            s = action_settings[gid]["custom"]
            count = s.get("warn_count", 1)
            s["warn_count"] = 1 if count >= 3 else count + 1
            return await show_custom_settings(q, gid)

        if data.startswith("change_custom_duration_"):
            gid = int(data.rsplit("_", 1)[1])
            opts = ["30m", "1h", "6h", "1d", "3d", "7d"]
            cur = action_settings[gid]["custom"]["duration"]
            action_settings[gid]["custom"]["duration"] = opts[(opts.index(cur)+1) % len(opts)]
            return await show_custom_settings(q, gid)

        if data.startswith("add_custom_message_"):
            gid = int(data.rsplit("_", 1)[1])
            user_state[uid] = {"state": "awaiting_custom_message", "gid": gid}
            await q.edit_message_text(
              "✏️ Please send your custom messages, separated by spaces like:\n\n"
              "`bio ib number`\n\n"
              "📌 Each word will be saved individually.",
              parse_mode="Markdown"
            )
            return

        await q.answer("❓ Unknown button!", show_alert=True)

    except Exception as e:
        logger.error(f"Callback Error: {e}")
        await q.edit_message_text("❌ Something went wrong, please try again.")
        
# /ban Command Handler
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_admin(chat_id, user_id, context):
        await message.reply_text("❌ Only admins can use this command!")
        return

    if not message.reply_to_message:
        return await message.reply_text("⛔ Please use this command in reply to a message.")

    target = message.reply_to_message.from_user

    if context.args:
        duration_str = context.args[0]
        duration = parse_duration(duration_str)
        until_date = datetime.utcnow() + duration
        duration_text = format_duration(duration)
    else:
        until_date = None
        duration_text = "permanently"

    try:
        await context.bot.ban_chat_member(chat_id, target.id, until_date=until_date)
        await message.reply_html(f"🚫 {target.mention_html()} has been banned for {duration_text}.")
    except Exception as e:
        logger.error(f"/ban error: {e}")
        await message.reply_text("❌ Failed to ban user.")


# /mute Command Handler
async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_admin(chat_id, user_id, context):
        await message.reply_text("❌ Only admins can use this command!")
        return

    if not message.reply_to_message:
        return await message.reply_text("🔇 Please use this command in reply to a message.")

    target = message.reply_to_message.from_user

    if context.args:
        duration_str = context.args[0]
        duration = parse_duration(duration_str)
        until_date = datetime.utcnow() + duration
        duration_text = format_duration(duration)
    else:
        until_date = None
        duration_text = "permanently"

    permissions = ChatPermissions(can_send_messages=False)

    try:
        await context.bot.restrict_chat_member(chat_id, target.id, permissions=permissions, until_date=until_date)
        await message.reply_html(f"🔇 {target.mention_html()} has been muted for {duration_text}.")
    except Exception as e:
        logger.error(f"/mute error: {e}")
        await message.reply_text("❌ Failed to mute user.")


# /warn Command Handler
async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_admin(chat_id, user_id, context):
        await message.reply_text("❌ Only admins can use this command!")
        return

    if not message.reply_to_message:
        return await message.reply_text("⚠️ Please use this command in reply to a message.")

    target_id = message.reply_to_message.from_user.id
    initialize_group_settings(chat_id)

    user_warnings[chat_id][target_id] = user_warnings[chat_id].get(target_id, 0) + 1
    count = user_warnings[chat_id][target_id]

    await message.reply_text(f"⚠️ Warning {count}/3 issued.")

    if count >= 3:
        await context.bot.ban_chat_member(chat_id, target_id, until_date=datetime.utcnow() + timedelta(hours=1))
        user_warnings[chat_id][target_id] = 0
        await message.reply_text("🚫 Too many warnings. User has been banned for 1 hour.")


# /unban Command Handler
async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_admin(chat_id, user_id, context):
        await message.reply_text("❌ Only admins can use this command!")
        return

    if not message.reply_to_message:
        return await message.reply_text("🟢 Reply to a user's message to unban.")

    target_id = message.reply_to_message.from_user.id

    try:
        member = await context.bot.get_chat_member(chat_id, target_id)

        if member.status != "kicked":
            return await message.reply_text("ℹ️ This user is not banned or already unbanned.")

        await context.bot.unban_chat_member(chat_id, target_id)
        await message.reply_text("✅ User has been unbanned.")

    except Exception as e:
        logger.error(f"/unban error: {e}")
        await message.reply_text("❌ Failed to unban user.")


# /unmute Command Handler
async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_admin(chat_id, user_id, context):
        return await message.reply_text("❌ Only admins can use this command!")

    if not message.reply_to_message:
        return await message.reply_text("🔓 Use this command by replying to the muted user's message.")

    target_id = message.reply_to_message.from_user.id

    try:
        # Get the member info
        member = await context.bot.get_chat_member(chat_id, target_id)

        # Check if already unrestricted
        if member.can_send_messages:
            return await message.reply_text("ℹ️ This user is already unmuted.")

        # Apply full permissions to unmute
        full_permissions = ChatPermissions(
            can_send_messages=True,
        )

        await context.bot.restrict_chat_member(chat_id, target_id, permissions=full_permissions)
        return await message.reply_text("✅ User has been unmuted.")

    except Exception as e:
        logger.error(f"/unmute error: {e}")
        return await message.reply_text("❌ Failed to unmute the user.")


# /settings command - Only for groups
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat = message.chat
    user_id = message.from_user.id
    chat_id = chat.id

    if not await is_admin(chat_id, user_id, context):
        await message.reply_text("❌ Only admins can use this command!")
        return

    if chat.type not in ["group", "supergroup"]:
        await message.reply_text("⚙️ This command is only available in group chats.")
        return

    initialize_group_settings(chat_id)
    await show_group_settings(update, chat_id)


# Admin Check Utility
async def is_admin(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        return any(a.user.id == user_id for a in admins)
    except Exception as e:
        logger.error(f"Admin check failed: {e}")
        return False


# Main
if __name__ == "__main__":
    TOKEN = "7735984673:AAGEhbsdIfO-j8B3DvBwBW9JSb9BcPd_J6o"  # Insert your bot token here
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", show_help))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("mute", mute_user))
    app.add_handler(CommandHandler("warn", warn_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("unmute", unmute_user))
    app.add_handler(CommandHandler("settings", settings_command))

    app.add_handler(CallbackQueryHandler(global_channel_settings, pattern="^channel_settings$"))
    app.add_handler(CallbackQueryHandler(toggle_forward_removal, pattern="^toggle_forward_removal$"))
    app.add_handler(CallbackQueryHandler(button_handler))

    # 👇 TEXT handlers must be last group (so commands don't get blocked)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, custom_message_input_handler), group=10)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_filter_handler), group=10)
    

    print("🤖 Bot is running...")
    app.run_polling()