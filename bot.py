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
from datetime import timedelta
import re

# لاگنگ سیٹ اپ
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# میموری ڈیٹا اسٹورز
group_settings: Dict[int, dict] = {}
action_settings: Dict[int, dict] = {}
user_chats: Dict[int, Dict[str, Set[int]]] = {}  # گروپس اور چینلز کو سیٹ میں اسٹور کرنا
user_warnings: Dict[int, Dict[int, int]] = {}  # چیٹ آئی ڈی -> {یوزر آئی ڈی: وارننگز کاؤنٹ}
admin_list: Dict[int, List[int]] = {}  # چیٹ آئی ڈی -> ایڈمنز کی فہرست

# مدت کی مددگار فنکشنز

def parse_duration(duration_str: str) -> timedelta:
    """
    duration_str کو پارس کر کے timedelta واپس کرتا ہے۔
    سپورٹ شدہ فارمیٹس: 30m, 1h, 6h, 1d, 3d, 7d
    یا انگریزی الفاظ: "30 minutes", "1 hour", "3 days" وغیرہ۔
    اگر انپٹ غلط ہو یا خالی ہو تو 1 گھنٹہ ڈیفالٹ ہوتا ہے۔
    """
    if not duration_str:
        return timedelta(hours=1)

    duration_str = duration_str.strip().lower()

    # regex سے نمبرز اور یونٹس نکالیں
    match = re.match(r"(\d+)\s*(m|min|minute|minutes|h|hr|hour|hours|d|day|days)?", duration_str)
    if not match:
        # اگر میچ نہ ہوا تو 1 گھنٹہ واپس کریں
        return timedelta(hours=1)

    value = int(match.group(1))
    unit = match.group(2)

    if unit is None:
        # اگر یونٹ نہ دیا تو ڈیفالٹ گھنٹہ سمجھیں
        unit = "h"

    if unit.startswith("m"):
        return timedelta(minutes=value)
    elif unit.startswith("h"):
        return timedelta(hours=value)
    elif unit.startswith("d"):
        return timedelta(days=value)
    else:
        return timedelta(hours=1)


def format_duration(duration: timedelta) -> str:
    """
    timedelta لے کر اردو میں پڑھنے کے قابل سٹرنگ واپس کرے گا۔
    """
    days = duration.days
    seconds = duration.seconds
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60

    if days > 0:
        return f"{days} دن"
    elif hours > 0:
        return f"{hours} گھنٹے"
    elif minutes > 0:
        return f"{minutes} منٹ"
    else:
        return "چند سیکنڈ"

# گروپ کی ڈیفالٹ سیٹنگز
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

# یوزر کے گروپس/چینلز ٹریک کرنا
def initialize_user_chats(user_id: int):
    if user_id not in user_chats:
        user_chats[user_id] = {"groups": set(), "channels": set()}
        
        
# /start ہینڈلر
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    initialize_user_chats(user_id)

    # کسی بھی صورت میں، message یا callback_query سے message حاصل کریں
    message = update.message or update.callback_query.message

    if message.chat.type == "private":
        keyboard = [
            [InlineKeyboardButton("➕ گروپ میں شامل کریں", url=f"https://t.me/{context.bot.username}?startgroup=true")],
            [InlineKeyboardButton("📊 میرے گروپس", callback_data="your_groups")],
            [InlineKeyboardButton("📢 میرے چینلز", callback_data="your_channels")],
            [InlineKeyboardButton("❓ مدد", callback_data="help_command")]
        ]
        await message.reply_text(
            "👋 گروپ مینجمنٹ بوٹ میں خوش آمدید!\n\n"
            "🔹 اپنے گروپس/چینلز میں شامل کریں\n"
            "🔹 سیٹنگز کو کنفیگر کریں\n"
            "🔹 ایڈمن ٹولز",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        cid = message.chat.id
        ctype = "channel" if message.chat.type == "channel" else "group"
        initialize_user_chats(user_id)
        user_chats[user_id][f"{ctype}s"].add(cid)
        initialize_group_settings(cid, ctype)
        await show_help(update, context)

# /help ہینڈلر
async def show_help(update_or_query: Union[Update, CallbackQueryHandler], context=None):
    text = """
🤖 *بوٹ کمانڈز*:

*ایڈمن کمانڈز:*
/ban [مدت] – صارف کو بین کریں (ریپلائی)
/mute [مدت] – صارف کو میوٹ کریں (ریپلائی)
/warn – صارف کو وارننگ دیں (ریپلائی)
/unban – صارف کو ان بین کریں
/unmute – صارف کو ان میوٹ کریں
/settings – سیٹنگز کو کنفیگر کریں
/allowlink [ڈومین] – ڈومین کو اجازت دیں
/blocklink [ڈومین] – ڈومین کو بلاک کریں

مثالیں:
/ban 1h – 1 گھنٹے کے لیے بین کریں
/mute 2d – 2 دن کے لیے میوٹ کریں
"""
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(text, parse_mode="Markdown")
    else:
        await update_or_query.edit_message_text(text, parse_mode="Markdown")


# یوزر کے گروپس کو بٹنز کی صورت میں دکھانا
async def show_user_groups(query):
    user_id = query.from_user.id
    groups = user_chats.get(user_id, {}).get("groups", set())
    if not groups:
        await query.edit_message_text("😕 آپ نے ابھی کسی گروپ میں اس بوٹ کو شامل نہیں کیا۔")
        return

    kb = []
    for gid in groups:
        kb.append([InlineKeyboardButton(f"گروپ: {gid}", callback_data=f"group_{gid}")])
    kb.append([InlineKeyboardButton("🏠 مینو", callback_data="force_start")])
    await query.edit_message_text("📊 آپ کے گروپس:", reply_markup=InlineKeyboardMarkup(kb))

async def show_user_channels(query):
    user_id = query.from_user.id
    channels = user_chats.get(user_id, {}).get("channels", set())
    if not channels:
        await query.edit_message_text("😕 آپ نے ابھی کسی چینل میں اس بوٹ کو شامل نہیں کیا۔")
        return

    kb = []
    for cid in channels:
        kb.append([InlineKeyboardButton(f"چینل: {cid}", callback_data=f"group_{cid}")])
    kb.append([InlineKeyboardButton("🏠 مینو", callback_data="force_start")])
    await query.edit_message_text("📢 آپ کے چینلز:", reply_markup=InlineKeyboardMarkup(kb))
    
    
# گروپ کی سیٹنگز مینو دکھانا
async def show_group_settings(update_or_query: Union[Update, CallbackQueryHandler], gid: int):
    initialize_group_settings(gid)
    kb = [
        [InlineKeyboardButton("🔗 لنک سیٹنگز", callback_data=f"link_settings_{gid}")],
        [InlineKeyboardButton("↩️ فارورڈ سیٹنگز", callback_data=f"forward_settings_{gid}")],
        [InlineKeyboardButton("🗣 مینشن سیٹنگز", callback_data=f"mention_settings_{gid}")],
        [InlineKeyboardButton("🔙 واپس", callback_data="your_groups")]  # تبدیل شدہ
    ]
    text = f"⚙️ *سیٹنگز برائے* `{gid}`\nزمرہ منتخب کریں:"
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    else:
        await update_or_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# لنک سیٹنگز سب مینو دکھانا
async def show_link_settings(query, gid):
    s = action_settings[gid]["links"]
    buttons = []

    # فلٹر آن/آف
    buttons.append([InlineKeyboardButton(
        f"✅ لنک فلٹرنگ: {'آن' if s['enabled'] else 'آف'}", 
        callback_data=f"toggle_links_enabled_{gid}"
    )])

    if s["enabled"]:
        # ایکشن بٹن (mute -> ban -> warn cycle)
        buttons.append([InlineKeyboardButton(
            f"🎯 ایکشن: {s['action'].capitalize()}",
            callback_data=f"cycle_link_action_{gid}"
        )])

        # اگر ایکشن warn ہو تو وارننگ لیول کا بٹن دکھائیں ورنہ نہیں
        if s['action'] == "warn":
            warn_count = s.get('warn_count', 1)
            buttons.append([InlineKeyboardButton(
                f"⚠️ وارننگ کی تعداد: {warn_count}",
                callback_data=f"cycle_link_warn_count_{gid}"
            )])

        # دورانیہ بٹن
        buttons.append([InlineKeyboardButton(
            f"⏰ دورانیہ: {s['duration']}",
            callback_data=f"change_link_duration_{gid}"
        )])

    # واپس بٹن
    buttons.append([InlineKeyboardButton("🔙 واپس", callback_data=f"group_settings_{gid}")])

    await query.edit_message_text(
        text="🔗 *لنک سیٹنگز*",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )

# فارورڈ سیٹنگز سب مینو دکھانا
async def show_forward_settings(query, gid):
    s = action_settings[gid]["forward"]
    buttons = [
        [InlineKeyboardButton(f"✅ فارورڈ فلٹر: {'آن' if s['enabled'] else 'آف'}", callback_data=f"toggle_forward_enabled_{gid}")],
    ]
    if s["enabled"]:
        buttons += [
            [InlineKeyboardButton(f"🎯 ایکشن: {s['action']}", callback_data=f"cycle_forward_action_{gid}")],
            [InlineKeyboardButton(f"⏰ دورانیہ: {s['duration']}", callback_data=f"change_forward_duration_{gid}")],
            [InlineKeyboardButton(f"⚠️ وارننگ: {'آن' if s['warn'] else 'آف'}", callback_data=f"toggle_forward_warn_{gid}")]
        ]
    buttons.append([InlineKeyboardButton("🔙 واپس", callback_data=f"group_settings_{gid}")])

    await query.edit_message_text(
        text="📤 *فارورڈ سیٹنگز*",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )

# مینشن سیٹنگز سب مینو دکھانا
async def show_mention_settings(query, gid):
    s = action_settings[gid]["mentions"]
    buttons = [
        [InlineKeyboardButton(f"✅ مینشن فلٹر: {'آن' if s['enabled'] else 'آف'}", callback_data=f"toggle_mention_enabled_{gid}")],
    ]
    if s["enabled"]:
        buttons += [
            [InlineKeyboardButton(f"🎯 ایکشن: {s['action']}", callback_data=f"cycle_mention_action_{gid}")],
            [InlineKeyboardButton(f"⏰ دورانیہ: {s['duration']}", callback_data=f"change_mention_duration_{gid}")],
            [InlineKeyboardButton(f"⚠️ وارننگ: {'آن' if s['warn'] else 'آف'}", callback_data=f"toggle_mention_warn_{gid}")]
        ]
    buttons.append([InlineKeyboardButton("🔙 واپس", callback_data=f"group_settings_{gid}")])

    await query.edit_message_text(
        text="👥 *مینشن سیٹنگز*",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )
    
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
        if settings["block_links"] and actions["links"]["enabled"] and has_links:
            await apply_action("links", chat_id, user_id, message, context)

        elif settings["block_forwards"] and actions["forward"]["enabled"] and is_forwarded:
            await apply_action("forward", chat_id, user_id, message, context)

        elif settings["block_mentions"] and actions["mentions"]["enabled"] and has_mentions:
            await apply_action("mentions", chat_id, user_id, message, context)

    except Exception as e:
        logger.error(f"فلٹر ہینڈلر ایرر: {e}")
        

async def apply_action(filter_type: str, chat_id: int, user_id: int, message, context):
    s = action_settings[chat_id][filter_type]
    action = s["action"]
    duration = parse_duration(s["duration"])

    # میسج ڈیلیٹ کریں
    await message.delete()

    # ایکشن اپلائی کریں
    if action == "mute":
        permissions = ChatPermissions(can_send_messages=False)
        until_date = datetime.utcnow() + duration
        await context.bot.restrict_chat_member(chat_id, user_id, permissions=permissions, until_date=until_date)
        await message.reply_text(f"🔇 یوزر کو {format_duration(duration)} کے لیے میوٹ کر دیا گیا۔", quote=False)

    elif action == "ban":
        until_date = datetime.utcnow() + duration
        await context.bot.ban_chat_member(chat_id, user_id, until_date=until_date)
        await message.reply_text(f"🚫 یوزر کو {format_duration(duration)} کے لیے بین کر دیا گیا۔", quote=False)

    elif action == "warn":
        user_warnings.setdefault(chat_id, {})
        user_warnings[chat_id][user_id] = user_warnings[chat_id].get(user_id, 0) + 1
        warn_count = user_warnings[chat_id][user_id]
        max_warn = s.get("warn_count", 3)

        await message.reply_text(f"⚠️ وارننگ {warn_count}/{max_warn} دی گئی۔", quote=False)

        if warn_count >= max_warn:
            # اب mute یا ban کریں
            if s.get("post_warn_action", "mute") == "ban":
                await context.bot.ban_chat_member(chat_id, user_id, until_date=datetime.utcnow() + duration)
                await message.reply_text(f"🚫 {warn_count} وارننگز کے بعد بین کر دیا گیا۔", quote=False)
            else:
                await context.bot.restrict_chat_member(chat_id, user_id, ChatPermissions(can_send_messages=False), until_date=datetime.utcnow() + duration)
                await message.reply_text(f"🔇 {warn_count} وارننگز کے بعد میوٹ کر دیا گیا۔", quote=False)
            user_warnings[chat_id][user_id] = 0

# تمام ان لائن بٹنز کے لیے مین ہینڈلر
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id
    await q.answer()

    try:
        if data == "force_start":
            return await start(update, context)
        if data == "your_groups":
            return await show_user_groups(q)
        if data == "your_channels":
            return await show_user_channels(q)
        if data == "help_command":
            return await show_help(q, context)
        
        # گروپ منتخب کرنے پر
        if data.startswith("group_"):
            gid = int(data.split("_",1)[1])
            if await is_admin(gid, uid, context):
                return await show_group_settings(q, gid)
            return await q.answer("⚠️ صرف ایڈمنز کے لیے!", show_alert=True)

        # گروپ سیٹنگز میں واپس جانے کے لیے
        if data.startswith("group_settings_"):
            gid = int(data.split("_",2)[2])
            if await is_admin(gid, uid, context):
                return await show_group_settings(q, gid)
            return await q.answer("⚠️ صرف ایڈمنز کے لیے!", show_alert=True)

        # لنک سیٹنگز دکھائیں
        if data.startswith("link_settings_"):
            gid = int(data.rsplit("_",1)[1])
            return await show_link_settings(q, gid)

        # فارورڈ سیٹنگز دکھائیں
        if data.startswith("forward_settings_"):
            gid = int(data.rsplit("_",1)[1])
            return await show_forward_settings(q, gid)

        # مینشن سیٹنگز دکھائیں
        if data.startswith("mention_settings_"):
            gid = int(data.rsplit("_",1)[1])
            return await show_mention_settings(q, gid)

        # 🔗 لنک سیٹنگز
        if data.startswith("toggle_links_enabled_"):
            gid = int(data.rsplit("_",1)[1])
            s = action_settings[gid]["links"]
            s['enabled'] = not s['enabled']
            if not s['enabled'] and s['action'] == 'delete':
                s['action'] = 'mute'
            return await show_link_settings(q, gid)

        if data.startswith("cycle_link_action_"):
            gid = int(data.rsplit("_",1)[1])
            s = action_settings[gid]["links"]
            options = ['mute', 'ban', 'warn']
            s['action'] = options[(options.index(s['action']) + 1) % len(options)]
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

        # 🔁 فارورڈ سیٹنگز
        if data.startswith("toggle_forward_enabled_"):
            gid = int(data.rsplit("_",1)[1])
            s = action_settings[gid]["forward"]
            s['enabled'] = not s['enabled']
            if not s['enabled'] and s['action'] == 'delete':
                s['action'] = 'mute'
            return await show_forward_settings(q, gid)

        if data.startswith("cycle_forward_action_"):
            gid = int(data.rsplit("_",1)[1])
            s = action_settings[gid]["forward"]
            options = ['mute', 'ban', 'warn']
            s['action'] = options[(options.index(s['action']) + 1) % len(options)]
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

        # 🗣 مینشن سیٹنگز
        if data.startswith("toggle_mention_enabled_"):
            gid = int(data.rsplit("_",1)[1])
            s = action_settings[gid]["mentions"]
            s['enabled'] = not s['enabled']
            if not s['enabled'] and s['action'] == 'delete':
                s['action'] = 'mute'
            return await show_mention_settings(q, gid)

        if data.startswith("cycle_mention_action_"):
            gid = int(data.rsplit("_",1)[1])
            s = action_settings[gid]["mentions"]
            options = ['mute', 'ban', 'warn']
            s['action'] = options[(options.index(s['action']) + 1) % len(options)]
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

        await q.answer("❓ نامعلوم بٹن!", show_alert=True)

    except Exception as e:
        logger.error(f"کال بیک ایرر: {e}")
        await q.edit_message_text("❌ کچھ غلط ہوگیا، دوبارہ کوشش کریں۔")
        
# /ban ہینڈلر
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_admin(chat_id, user_id, context):
        await message.reply_text("❌ صرف ایڈمنز اس کمانڈ کو استعمال کر سکتے ہیں!")
        return

    if not message.reply_to_message:
        return await message.reply_text("⛔ اس کمانڈ کو کسی میسج پر ریپلائی میں استعمال کریں۔")

    target = message.reply_to_message.from_user

    if context.args:
        duration_str = context.args[0]
        duration = parse_duration(duration_str)
        until_date = datetime.utcnow() + duration
        duration_text = format_duration(duration)
    else:
        until_date = None
        duration_text = "لامحدود مدت"

    try:
        await context.bot.ban_chat_member(chat_id, target.id, until_date=until_date)
        await message.reply_html(f"🚫 {target.mention_html()} کو {duration_text} کے لیے بین کر دیا گیا۔")
    except Exception as e:
        logger.error(f"/ban ایرر: {e}")
        await message.reply_text("❌ بین کرنے میں مسئلہ پیش آیا۔")
        
# /mute ہینڈلر
async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_admin(chat_id, user_id, context):
        await message.reply_text("❌ صرف ایڈمنز اس کمانڈ کو استعمال کر سکتے ہیں!")
        return

    if not message.reply_to_message:
        return await message.reply_text("🔇 اس کمانڈ کو کسی میسج پر ریپلائی میں استعمال کریں۔")

    target = message.reply_to_message.from_user

    # وقت چیک کریں
    if context.args:
        duration_str = context.args[0]
        duration = parse_duration(duration_str)
        until_date = datetime.utcnow() + duration
        duration_text = format_duration(duration)
    else:
        until_date = None
        duration_text = "لامحدود مدت"

    permissions = ChatPermissions(can_send_messages=False)

    try:
        await context.bot.restrict_chat_member(chat_id, target.id, permissions=permissions, until_date=until_date)
        await message.reply_html(f"🔇 {target.mention_html()} کو {duration_text} کے لیے میوٹ کر دیا گیا۔")
    except Exception as e:
        logger.error(f"/mute ایرر: {e}")
        await message.reply_text("❌ میوٹ کرنے میں مسئلہ پیش آیا۔")
        
# /warn ہینڈلر
async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_admin(chat_id, user_id, context):
        await message.reply_text("❌ صرف ایڈمنز اس کمانڈ کو استعمال کر سکتے ہیں!")
        return

    if not message.reply_to_message:
        return await message.reply_text("⚠️ اس کمانڈ کو کسی میسج پر ریپلائی میں استعمال کریں۔")

    target_id = message.reply_to_message.from_user.id
    initialize_group_settings(chat_id)

    user_warnings[chat_id][target_id] = user_warnings[chat_id].get(target_id, 0) + 1
    count = user_warnings[chat_id][target_id]

    await message.reply_text(f"⚠️ وارننگ {count}/3 دے دی گئی۔")

    if count >= 3:
        await context.bot.ban_chat_member(chat_id, target_id, until_date=datetime.utcnow() + timedelta(hours=1))
        user_warnings[chat_id][target_id] = 0
        await message.reply_text("🚫 حد سے زیادہ وارننگز۔ 1 گھنٹے کے لیے بین کر دیا گیا۔")
        
# /unban ہینڈلر
async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_admin(chat_id, user_id, context):
        await message.reply_text("❌ صرف ایڈمنز اس کمانڈ کو استعمال کر سکتے ہیں!")
        return

    if not message.reply_to_message:
        return await message.reply_text("🟢 ان بین کرنے کے لیے کسی یوزر کے میسج پر ریپلائی کریں۔")

    target_id = message.reply_to_message.from_user.id

    try:
        member = await context.bot.get_chat_member(chat_id, target_id)

        if member.status != "kicked":
            return await message.reply_text("ℹ️ یہ یوزر پہلے ہی ان بین ہے یا بین نہیں تھا۔")

        await context.bot.unban_chat_member(chat_id, target_id)
        await message.reply_text("✅ یوزر کو ان بین کر دیا گیا۔")

    except Exception as e:
        logger.error(f"/unban ایرر: {e}")
        await message.reply_text("❌ ان بین کرنے میں مسئلہ ہوا۔")

# /unmute ہینڈلر
async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_admin(chat_id, user_id, context):
        await message.reply_text("❌ صرف ایڈمنز اس کمانڈ کو استعمال کر سکتے ہیں!")
        return

    if not message.reply_to_message:
        return await message.reply_text("🔓 کسی میسج پر ریپلائی کر کے ان میوٹ کریں۔")

    target_id = message.reply_to_message.from_user.id

    try:
        member = await context.bot.get_chat_member(chat_id, target_id)

        if member.status != "restricted":
            return await message.reply_text("ℹ️ یہ یوزر میوٹ نہیں ہے۔")

        if member.can_send_messages:
            return await message.reply_text("ℹ️ یہ یوزر پہلے ہی ان میوٹ ہے۔")

        full_permissions = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_change_info=False,
            can_invite_users=True,
            can_pin_messages=False
        )

        await context.bot.restrict_chat_member(chat_id, target_id, permissions=full_permissions)
        await message.reply_text("🔓 یوزر کو ان میوٹ کر دیا گیا۔")

    except Exception as e:
        logger.error(f"/unmute ایرر: {e}")
        await message.reply_text("❌ ان میوٹ کرنے میں مسئلہ ہوا۔")
        
# /settings کمانڈ ہینڈلر - صرف گروپ چیٹس کے لیے
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat = message.chat
    user_id = message.from_user.id
    chat_id = chat.id
    
    if not await is_admin(chat_id, user_id, context):
        await message.reply_text("❌ صرف ایڈمنز اس کمانڈ کو استعمال کر سکتے ہیں!")
        return

    if chat.type not in ["group", "supergroup"]:
        await message.reply_text("⚙️ یہ کمانڈ صرف گروپ چیٹس میں دستیاب ہے۔")
        return

    if not await is_admin(chat_id, user_id, context):
        await message.reply_text("❌ صرف ایڈمن اس کمانڈ کو استعمال کر سکتے ہیں۔")
        return

    initialize_group_settings(chat_id)
    await show_group_settings(update, chat_id)
        
# ایڈمن حقوق چیک کرنا
async def is_admin(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        return any(a.user.id == user_id for a in admins)
    except Exception as e:
        logger.error(f"ایڈمن چیک ناکام: {e}")
        return False


# مین
if __name__ == "__main__":
    TOKEN = "7735984673:AAGEhbsdIfO-j8B3DvBwBW9JSb9BcPd_J6o"  # اپنا بوٹ ٹوکن یہاں ڈالیں
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", show_help))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("mute", mute_user))
    app.add_handler(CommandHandler("warn", warn_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("unmute", unmute_user))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_filter_handler))

    print("🤖 بوٹ چل رہا ہے...")
    app.run_polling()
