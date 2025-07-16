import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)
from datetime import timedelta

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ڈیٹا اسٹور (سادہ dicts)
user_chats = {}  # user_id -> {"groups": set(), "channels": set()}
group_settings = {}  # group_id -> settings dict
action_settings = {}  # group_id -> {"links":{}, "forward":{}, "mention":{}}
user_warnings = {}  # group_id -> user_id -> count
custom_messages = {}  # group_id -> list of {"text":str, "action":str, "duration":str}

# کنورسیشن اسٹیٹس
ADDING_CUSTOM_MSG = range(1)

# -- یوزر چٹ انیشیلائز --
def initialize_user_chats(user_id):
    if user_id not in user_chats:
        user_chats[user_id] = {"groups": set(), "channels": set()}

# -- گروپ سیٹنگز انیشیلائز --
def initialize_group_settings(group_id):
    if group_id not in group_settings:
        group_settings[group_id] = {
            "block_links": False,
            "block_forwards": False,
            "remove_forward_tag": False,
            "allowed_domains": set(),
        }
    if group_id not in action_settings:
        action_settings[group_id] = {
            "links": {
                "enabled": False,
                "action": "delete",  # delete/mute/ban/warn
                "warn": True,
                "warn_limit": 3,
                "duration": "1h",
            },
            "forward": {
                "enabled": False,
                "action": "delete",
                "warn": True,
                "warn_limit": 3,
                "duration": "1h",
            },
            "mention": {
                "enabled": False,
                "action": "delete",
                "warn": True,
                "warn_limit": 3,
                "duration": "1h",
            },
        }
    if group_id not in user_warnings:
        user_warnings[group_id] = {}
    if group_id not in custom_messages:
        custom_messages[group_id] = []

# -- اسٹارٹ کمانڈ --
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    initialize_user_chats(user.id)

    keyboard = [
        [InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
        [InlineKeyboardButton("📊 Your Groups", callback_data="your_groups")],
        [InlineKeyboardButton("📢 Your Channels", callback_data="your_channels")],
        [InlineKeyboardButton("❓ Help", callback_data="help_command")],
    ]
    await update.message.reply_text(
        f"👋 Welcome {user.first_name}!\n\nUse the buttons below to manage your groups and channels.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

# -- ہیلپ مینو --
async def show_help(update_or_query, context=None):
    text = (
        "🤖 *Bot Commands:*\n\n"
        "/ban [time] - Ban user (reply)\n"
        "/mute [time] - Mute user (reply)\n"
        "/warn - Warn user (reply)\n"
        "/unban - Unban user\n"
        "/unmute - Unmute user\n"
        "/settings - Open settings\n\n"
        "Example:\n"
        "/ban 1h - Ban for 1 hour\n"
        "/mute 2d - Mute for 2 days"
    )
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(text, parse_mode="Markdown")
    else:
        await update_or_query.edit_message_text(text, parse_mode="Markdown")

# -- Your Groups مینو دکھائیں --
async def show_user_groups(query):
    user_id = query.from_user.id
    initialize_user_chats(user_id)
    groups = user_chats[user_id]["groups"]
    if not groups:
        await query.edit_message_text(
            "You have no groups added.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="start")]])
        )
        return

    keyboard = []
    for gid in groups:
        try:
            chat = await query.bot.get_chat(int(gid))
            keyboard.append([InlineKeyboardButton(chat.title, callback_data=f"group_{gid}_settings")])
        except Exception as e:
            logger.warning(f"Failed to get chat {gid}: {e}")

    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="start")])
    await query.edit_message_text(
        "Select a group to configure:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

# -- گروپ سیٹنگز مینو --
async def show_group_settings(query, group_id):
    initialize_group_settings(group_id)
    keyboard = [
        [InlineKeyboardButton("🔗 Link Settings", callback_data=f"link_settings_{group_id}")],
        [InlineKeyboardButton("↩️ Forward Settings", callback_data=f"forward_settings_{group_id}")],
        [InlineKeyboardButton("🗣 Mention Settings", callback_data=f"mention_settings_{group_id}")],
        [InlineKeyboardButton("💬 Custom Messages", callback_data=f"custommsg_settings_{group_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="your_groups")],
    ]
    await query.edit_message_text("Group Settings - Select an option:", reply_markup=InlineKeyboardMarkup(keyboard))

# -- لنک سیٹنگز مینو --
async def show_link_settings(query, group_id):
    s = action_settings[group_id]["links"]
    keyboard = [
        [InlineKeyboardButton(f"Enabled: {'Yes' if s['enabled'] else 'No'}", callback_data=f"toggle_links_enabled_{group_id}")],
        [InlineKeyboardButton(f"Action: {s['action'].capitalize()}", callback_data=f"cycle_link_action_{group_id}")],
        [InlineKeyboardButton(f"Warn Enabled: {'Yes' if s['warn'] else 'No'}", callback_data=f"toggle_link_warn_{group_id}")],
        [InlineKeyboardButton(f"Warn Limit: {s['warn_limit']}", callback_data=f"change_link_warnlimit_{group_id}")],
        [InlineKeyboardButton(f"Duration: {s['duration']}", callback_data=f"change_link_duration_{group_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"group_{group_id}_settings")],
    ]
    await query.edit_message_text("Link Settings:", reply_markup=InlineKeyboardMarkup(keyboard))

# -- فارورڈ سیٹنگز مینو --
async def show_forward_settings(query, group_id):
    s = action_settings[group_id]["forward"]
    keyboard = [
        [InlineKeyboardButton(f"Enabled: {'Yes' if s['enabled'] else 'No'}", callback_data=f"toggle_forward_enabled_{group_id}")],
        [InlineKeyboardButton(f"Action: {s['action'].capitalize()}", callback_data=f"cycle_forward_action_{group_id}")],
        [InlineKeyboardButton(f"Warn Enabled: {'Yes' if s['warn'] else 'No'}", callback_data=f"toggle_forward_warn_{group_id}")],
        [InlineKeyboardButton(f"Warn Limit: {s['warn_limit']}", callback_data=f"change_forward_warnlimit_{group_id}")],
        [InlineKeyboardButton(f"Duration: {s['duration']}", callback_data=f"change_forward_duration_{group_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"group_{group_id}_settings")],
    ]
    await query.edit_message_text("Forward Settings:", reply_markup=InlineKeyboardMarkup(keyboard))

# -- مینشن سیٹنگز مینو --
async def show_mention_settings(query, group_id):
    s = action_settings[group_id]["mention"]
    keyboard = [
        [InlineKeyboardButton(f"Enabled: {'Yes' if s['enabled'] else 'No'}", callback_data=f"toggle_mention_enabled_{group_id}")],
        [InlineKeyboardButton(f"Action: {s['action'].capitalize()}", callback_data=f"cycle_mention_action_{group_id}")],
        [InlineKeyboardButton(f"Warn Enabled: {'Yes' if s['warn'] else 'No'}", callback_data=f"toggle_mention_warn_{group_id}")],
        [InlineKeyboardButton(f"Warn Limit: {s['warn_limit']}", callback_data=f"change_mention_warnlimit_{group_id}")],
        [InlineKeyboardButton(f"Duration: {s['duration']}", callback_data=f"change_mention_duration_{group_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"group_{group_id}_settings")],
    ]
    await query.edit_message_text("Mention Settings:", reply_markup=InlineKeyboardMarkup(keyboard))

# -- کسٹم میسجز مینو --
async def show_custommsg_settings(query, group_id):
    msgs = custom_messages.get(group_id, [])
    keyboard = []
    for idx, msg in enumerate(msgs):
        short_text = msg['text'] if len(msg['text']) <= 20 else msg['text'][:20] + "..."
        keyboard.append([InlineKeyboardButton(f"🗑 Delete: {short_text}", callback_data=f"del_custommsg_{group_id}_{idx}")])
    keyboard.append([InlineKeyboardButton("➕ Add New Message", callback_data=f"add_custommsg_{group_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data=f"group_{group_id}_settings")])
    await query.edit_message_text("Custom Messages - Add or Delete:", reply_markup=InlineKeyboardMarkup(keyboard))

# -- Callback query ہینڈلر --
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    await query.answer()

    # سادہ بیک بٹن ہینڈلنگ
    if data == "start":
        await start(update, context)
        return
    if data == "your_groups":
        await show_user_groups(query)
        return
    if data == "your_channels":
        await query.edit_message_text("Channels not implemented yet.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="start")]]))
        return
    if data == "help_command":
        await show_help(query, context)
        return

    # گروپ سیٹنگز کے لیے
    if data.endswith("_settings"):
        parts = data.split("_")
        if len(parts) >= 3:
            group_id = parts[1]
            # ایڈمن چیک کرلیں
            if not await is_admin(int(group_id), user_id, context):
                await query.answer("Only admins allowed!", show_alert=True)
                return
            if parts[0] == "group":
                await show_group_settings(query, group_id)
                return

    # لنک سیٹنگز کنٹرولز
    if data.startswith("toggle_links_enabled_"):
        gid = data.split("_")[3]
        if not await is_admin(int(gid), user_id, context):
            await query.answer("Only admins allowed!", show_alert=True)
            return
        s = action_settings[gid]["links"]
        s["enabled"] = not s["enabled"]
        await show_link_settings(query, gid)
        return

    if data.startswith("cycle_link_action_"):
        gid = data.split("_")[3]
        if not await is_admin(int(gid), user_id, context):
            await query.answer("Only admins allowed!", show_alert=True)
            return
        actions = ["delete", "mute", "ban", "warn"]
        s = action_settings[gid]["links"]
        current = s["action"]
        next_idx = (actions.index(current) + 1) % len(actions)
        s["action"] = actions[next_idx]
        await show_link_settings(query, gid)
        return

    if data.startswith("toggle_link_warn_"):
        gid = data.split("_")[3]
        if not await is_admin(int(gid), user_id, context):
            await query.answer("Only admins allowed!", show_alert=True)
            return
        s = action_settings[gid]["links"]
        s["warn"] = not s["warn"]
        await show_link_settings(query, gid)
        return

    if data.startswith("change_link_warnlimit_"):
        gid = data.split("_")[3]
        if not await is_admin(int(gid), user_id, context):
            await query.answer("Only admins allowed!", show_alert=True)
            return
        s = action_settings[gid]["links"]
        warn_limits = [1, 2, 3, 4, 5]
        current = s.get("warn_limit", 3)
        next_idx = (warn_limits.index(current) + 1) % len(warn_limits)
        s["warn_limit"] = warn_limits[next_idx]
        await show_link_settings(query, gid)
        return

    if data.startswith("change_link_duration_"):
        gid = data.split("_")[3]
        if not await is_admin(int(gid), user_id, context):
            await query.answer("Only admins allowed!", show_alert=True)
            return
        s = action_settings[gid]["links"]
        durations = ["30m", "1h", "2h", "6h", "1d", "3d", "7d", "perm"]
        current = s["duration"]
        next_idx = (durations.index(current) + 1) % len(durations)
        s["duration"] = durations[next_idx]
        await show_link_settings(query, gid)
        return

    # فارورڈ، مینشن سیٹنگز کے لیے بھی اسی طرح کوڈ بنائیں
    # یہاں میں ایک ہی مثال دیتا ہوں، باقی آپ خود آسانی سے ایڈ کر سکتے ہیں

    if data.startswith("custommsg_settings_"):
        gid = data.split("_")[2]
        if not await is_admin(int(gid), user_id, context):
            await query.answer("Only admins allowed!", show_alert=True)
            return
        await show_custommsg_settings(query, gid)
        return

    if data.startswith("add_custommsg_"):
        gid = data.split("_")[1]
        if not await is_admin(int(gid), user_id, context):
            await query.answer("Only admins allowed!", show_alert=True)
            return
        # شروع کریں کنورسیشن نئے میسج کے لیے
        context.user_data["add_custommsg_group"] = gid
        await query.message.reply_text("Please send the custom message text you want to add:")
        return ADDING_CUSTOM_MSG

    if data.startswith("del_custommsg_"):
        parts = data.split("_")
        gid = parts[2]
        idx = int(parts[3])
        if not await is_admin(int(gid), user_id, context):
            await query.answer("Only admins allowed!", show_alert=True)
            return
        msgs = custom_messages.get(gid, [])
        if 0 <= idx < len(msgs):
            msgs.pop(idx)
            custom_messages[gid] = msgs
            await show_custommsg_settings(query, gid)
        else:
            await query.answer("Invalid index!", show_alert=True)
        return

    # بیک بٹن ہینڈلنگ
    if data == "your_groups_back" or data == "back":
        await show_user_groups(query)
        return

    # Default
    await query.answer("Unknown action!", show_alert=True)

# -- کسٹم میسج ایڈ کرنے کا ہینڈلر --
async def receive_custommsg_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    gid = context.user_data.get("add_custommsg_group")
    if not gid:
        await update.message.reply_text("Group info not found. Please try again.")
        return ConversationHandler.END

    msg_entry = {"text": text, "action": "mute", "duration": "1h"}  # Default action, آپ اپنی مرضی سے بدل سکتے ہیں
    custom_messages.setdefault(gid, []).append(msg_entry)
    await update.message.reply_text(f"Custom message added for group {gid}.")
    # واپس کسٹم میسجز مینو دکھائیں
    chat = update.effective_chat
    # بس start نہ کریں بلکہ keyboard بھی اپڈیٹ کریں
    # آپ کی آسانی کے لیے:
    del context.user_data["add_custommsg_group"]
    # یہاں سادہ reply_markup کے ساتھ پیغام بھیجیں یا اگر آپ چاہتے ہیں تو callback_query.edit_message_text سے بھی کر سکتے ہیں
    return ConversationHandler.END

# -- ایڈمن چیک (سادہ) --
async def is_admin(chat_id, user_id, context):
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        for admin in admins:
            if admin.user.id == user_id:
                return True
        return False
    except Exception as e:
        logger.error(f"Admin check error: {e}")
        return False

# -- مین فنکشن اور ہینڈلرز رجسٹر کرنا --
def main():
    app = ApplicationBuilder().token("7735984673:AAGEhbsdIfO-j8B3DvBwBW9JSb9BcPd_J6o").build()

    conv_handler = ConversationHandler(
        entry_points=[],
        states={
            ADDING_CUSTOM_MSG: [MessageHandler(filters.TEXT & (~filters.COMMAND), receive_custommsg_text)],
        },
        fallbacks=[],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(conv_handler)

    app.run_polling()

if __name__ == "__main__":
    main()
