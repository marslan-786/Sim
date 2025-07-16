import logging
from telegram import Update, ChatPermissions
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# لوگنگ سیٹ اپ کریں
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# یوزر وارننگز کو اسٹور کرنے کے لیے ڈکشنری
user_warnings = {}

class GroupManagementBot:
    def __init__(self, token):
        self.updater = Updater(token, use_context=True)
        self.dispatcher = self.updater.dispatcher
        
        # کمانڈ ہینڈلرز
        self.dispatcher.add_handler(CommandHandler("start", self.start))
        self.dispatcher.add_handler(CommandHandler("warn", self.warn_user))
        self.dispatcher.add_handler(CommandHandler("mute", self.mute_user))
        self.dispatcher.add_handler(CommandHandler("ban", self.ban_user))
        self.dispatcher.add_handler(CommandHandler("unban", self.unban_user))
        self.dispatcher.add_handler(CommandHandler("settings", self.group_settings))
        
        # میسج ہینڈلرز
        self.dispatcher.add_handler(MessageHandler(Filters.text | Filters.photo | Filters.video | Filters.document | Filters.forwarded, self.message_filter))
        
    def start(self, update: Update, context: CallbackContext):
        update.message.reply_text('گروپ مینیجمنٹ بوٹ فعال ہے!')
        
    def warn_user(self, update: Update, context: CallbackContext):
        if not update.message.reply_to_message:
            update.message.reply_text('کسی پیغام کو ریپلائی کر کے کمانڈ استعمال کریں۔')
            return
            
        user = update.message.reply_to_message.from_user
        chat_id = update.message.chat_id
        
        if chat_id not in user_warnings:
            user_warnings[chat_id] = {}
            
        if user.id not in user_warnings[chat_id]:
            user_warnings[chat_id][user.id] = 0
            
        user_warnings[chat_id][user.id] += 1
        
        if user_warnings[chat_id][user.id] >= 3:
            self.mute_user(update, context)
            update.message.reply_text(f'کارروائی: صارف {user.name} کو 3 وارننگز مل چکی ہیں۔ میوٹ کر دیا گیا۔')
        else:
            update.message.reply_text(f'انتباہ: صارف {user.name} کو وارننگ دی گئی۔ کل وارننگز: {user_warnings[chat_id][user.id]}/3')
    
    def mute_user(self, update: Update, context: CallbackContext):
        if not update.message.reply_to_message:
            update.message.reply_text('کسی پیغام کو ریپلائی کر کے کمانڈ استعمال کریں۔')
            return
            
        user = update.message.reply_to_message.from_user
        chat_id = update.message.chat_id
        
        try:
            context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user.id,
                permissions=ChatPermissions(
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False
                )
            )
            update.message.reply_text(f'صارف {user.name} کو میوٹ کر دیا گیا۔')
        except Exception as e:
            update.message.reply_text(f'خرابی: {str(e)}')
    
    def ban_user(self, update: Update, context: CallbackContext):
        if not update.message.reply_to_message:
            update.message.reply_text('کسی پیغام کو ریپلائی کر کے کمانڈ استعمال کریں۔')
            return
            
        user = update.message.reply_to_message.from_user
        chat_id = update.message.chat_id
        
        try:
            context.bot.ban_chat_member(chat_id=chat_id, user_id=user.id)
            update.message.reply_text(f'صارف {user.name} کو بین کر دیا گیا۔')
        except Exception as e:
            update.message.reply_text(f'خرابی: {str(e)}')
    
    def unban_user(self, update: Update, context: CallbackContext):
        if not context.args:
            update.message.reply_text('صارف ID درج کریں: /unban <user_id>')
            return
            
        user_id = int(context.args[0])
        chat_id = update.message.chat_id
        
        try:
            context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
            update.message.reply_text(f'صارف {user_id} کو انبین کر دیا گیا۔')
        except Exception as e:
            update.message.reply_text(f'خرابی: {str(e)}')
    
    def group_settings(self, update: Update, context: CallbackContext):
        update.message.reply_text('گروپ سیٹنگز مینیو: ...')  # یہاں آپ مزید فنکشنلٹی شامل کر سکتے ہیں
    
    def message_filter(self, update: Update, context: CallbackContext):
        # سپیم اور لنک کنٹرول
        message = update.message
        chat_id = message.chat_id
        user = message.from_user
        
        # لنک چیک کریں
        if message.entities and any(entity.type == "url" for entity in message.entities):
            message.delete()
            self.warn_user_auto(update, context, "لنک شیئر کرنے پر")
            return
            
        # فارورڈ میسج چیک کریں
        if message.forward_from or message.forward_from_chat:
            message.delete()
            self.warn_user_auto(update, context, "فارورڈ میسج کرنے پر")
            return
    
    def warn_user_auto(self, update: Update, context: CallbackContext, reason: str):
        user = update.message.from_user
        chat_id = update.message.chat_id
        
        if chat_id not in user_warnings:
            user_warnings[chat_id] = {}
            
        if user.id not in user_warnings[chat_id]:
            user_warnings[chat_id][user.id] = 0
            
        user_warnings[chat_id][user.id] += 1
        
        warning_msg = f"خودکار انتباہ: صارف {user.name} کو {reason} وارننگ دی گئی۔ کل وارننگز: {user_warnings[chat_id][user.id]}/3"
        
        if user_warnings[chat_id][user.id] >= 3:
            self.mute_user(update, context)
            warning_msg += "\nکارروائی: صارف کو میوٹ کر دیا گیا۔"
        
        context.bot.send_message(chat_id=chat_id, text=warning_msg)

if __name__ == '__main__':
    # اپنا بوٹ ٹوکن یہاں درج کریں
    TOKEN = "8017193630:AAFaMRpJ7Hk-2MTibaWOR_71-NYuFgr_2_U"
    
    bot = GroupManagementBot(TOKEN)
    bot.updater.start_polling()
    bot.updater.idle()
