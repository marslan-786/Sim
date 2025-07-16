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

    if update.message.chat.type == "private":
        keyboard = [
            [InlineKeyboardButton("➕ گروپ میں شامل کریں", url=f"https://t.me/{context.bot.username}?startgroup=true")],
            [InlineKeyboardButton("📊 میرے گروپس", callback_data="your_groups")],
            [InlineKeyboardButton("📢 میرے چینلز", callback_data="your_channels")],
            [InlineKeyboardButton("❓ مدد", callback_data="help_command")]
        ]
        await update.message.reply_text(
            "👋 گروپ مینجمنٹ بوٹ میں خوش آمدید!\n\n"
            "🔹 اپنے گروپس/چینلز میں شامل کریں\n"
            "🔹 سیٹنگز کو کنفیگر کریں\n"
            "🔹 ایڈمن ٹولز",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        cid = update.message.chat.id
        ctype = "channel" if update.message.chat.type == "channel" else "group"
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
    kb.append([InlineKeyboardButton("🏠 مینو", callback_data="start")])  # تبدیل شدہ
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
    kb.append([InlineKeyboardButton("🏠 مینو", callback_data="start")])  # تبدیل شدہ
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
async def show_link_settings(query: CallbackQueryHandler, gid: int):
    s = action_settings[gid]["links"]
    kb = [
        [InlineKeyboardButton(f"فعال: {'✅' if s['enabled'] else '❌'}", callback_data=f"toggle_links_enabled_{gid}")],
        [InlineKeyboardButton(f"کارروائی: {s['action']}", callback_data=f"cycle_link_action_{gid}")],
        [InlineKeyboardButton(f"مدت: {s['duration']}", callback_data=f"change_link_duration_{gid}")],
        [InlineKeyboardButton(f"وارننگ: {'✅' if s['warn'] else '❌'}", callback_data=f"toggle_link_warn_{gid}")],
        [InlineKeyboardButton("🔙 واپس", callback_data=f"group_settings_{gid}")]  # تبدیل شدہ
    ]
    await query.edit_message_text("🔗 *لنک سیٹنگز*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# فارورڈ سیٹنگز سب مینو دکھانا
async def show_forward_settings(query: CallbackQueryHandler, gid: int):
    s = action_settings[gid]["forward"]
    kb = [
        [InlineKeyboardButton(f"فعال: {'✅' if s['enabled'] else '❌'}", callback_data=f"toggle_forward_enabled_{gid}")],
        [InlineKeyboardButton(f"کارروائی: {s['action']}", callback_data=f"cycle_forward_action_{gid}")],
        [InlineKeyboardButton(f"مدت: {s['duration']}", callback_data=f"change_forward_duration_{gid}")],
        [InlineKeyboardButton(f"وارننگ: {'✅' if s['warn'] else '❌'}", callback_data=f"toggle_forward_warn_{gid}")],
        [InlineKeyboardButton("🔙 واپس", callback_data=f"group_settings_{gid}")]  # تبدیل شدہ
    ]
    await query.edit_message_text("↩️ *فارورڈ سیٹنگز*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# مینشن سیٹنگز سب مینو دکھانا
async def show_mention_settings(query: CallbackQueryHandler, gid: int):
    s = action_settings[gid]["mentions"]
    kb = [
        [InlineKeyboardButton(f"فعال: {'✅' if s['enabled'] else '❌'}", callback_data=f"toggle_mention_enabled_{gid}")],
        [InlineKeyboardButton(f"کارروائی: {s['action']}", callback_data=f"cycle_mention_action_{gid}")],
        [InlineKeyboardButton(f"مدت: {s['duration']}", callback_data=f"change_mention_duration_{gid}")],
        [InlineKeyboardButton(f"وارننگ: {'✅' if s['warn'] else '❌'}", callback_data=f"toggle_mention_warn_{gid}")],
        [InlineKeyboardButton("🔙 واپس", callback_data=f"group_settings_{gid}")]  # تبدیل شدہ
    ]
    await query.edit_message_text("🗣 *مینشن سیٹنگز*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    
    
# تمام ان لائن بٹنز کے لیے مین ہینڈلر
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id
    await q.answer()

    try:
        if data == "force_start":
            # یوزر کی طرف سے /start بھیجنے کا بٹن
            keyboard = [[InlineKeyboardButton(
                "🔄 مینو ری لوڈ کریں", 
                switch_inline_query_current_chat="/start"
            )]]
            await q.edit_message_text(
                "مینو پر واپس جانے کے لیے نیچے دیے گئے بٹن پر کلک کریں:",
                reply_markup=InlineKeyboardMarkup(keyboard)
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
            return await q.answer("⚠️ صرف ایڈمنز کے لیے!", show_alert=True)

        # گروپ سیٹنگز واپس جانے کے لیے
        if data.startswith("group_settings_"):
            gid = int(data.split("_",2)[2])
            if await is_admin(gid, uid, context):
                return await show_group_settings(q, gid)
            return await q.answer("⚠️ صرف ایڈمنز کے لیے!", show_alert=True)

        # لنک ٹوگلز
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

        # فارورڈ ٹوگلز
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

        # مینشن ٹوگلز
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

        await q.answer("نامعلوم بٹن!", show_alert=True)
    except Exception as e:
        logger.error(f"کال بیک ایرر: {e}")
        await q.edit_message_text("❌ کچھ غلط ہوگیا، دوبارہ کوشش کریں۔")
        
        
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

    print("🤖 بوٹ چل رہا ہے...")
    app.run_polling()
