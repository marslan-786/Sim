import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    CallbackQueryHandler
)
from datetime import datetime, timedelta
import pytz
import re

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database simulation (replace with real database in production)
group_settings = {}
user_warnings = {}
allowed_links = {}  # Group-specific allowed domains

class EnhancedGroupBot:
    def __init__(self, token):
        self.updater = Updater(token, use_context=True)
        self.dispatcher = self.updater.dispatcher
        
        # Add handlers
        self.dispatcher.add_handler(CommandHandler("start", self.start))
        self.dispatcher.add_handler(CommandHandler("settings", self.group_settings_command))
        self.dispatcher.add_handler(CommandHandler("ban", self.ban_user))
        self.dispatcher.add_handler(CommandHandler("mute", self.mute_user))
        self.dispatcher.add_handler(CommandHandler("warn", self.warn_user))
        self.dispatcher.add_handler(CommandHandler("unban", self.unban_user))
        self.dispatcher.add_handler(CommandHandler("unmute", self.unmute_user))
        self.dispatcher.add_handler(CommandHandler("allowlink", self.allow_link, pass_args=True))
        self.dispatcher.add_handler(CommandHandler("blocklink", self.block_link, pass_args=True))
        
        self.dispatcher.add_handler(CallbackQueryHandler(self.button_handler))
        
        self.dispatcher.add_handler(
            MessageHandler(
                Filters.text | Filters.photo | Filters.video | Filters.document | Filters.forwarded,
                self.message_filter
            )
        )
    
    def initialize_group_settings(self, chat_id):
        """Initialize default settings for a group"""
        if chat_id not in group_settings:
            group_settings[chat_id] = {
                "block_links": True,
                "block_forwards": True,
                "block_mentions": False,
                "warn_on_spam": True,
                "auto_mute": True,
                "mute_duration": "1d",  # Default mute duration (1 day)
                "max_warnings": 3,
                "allowed_domains": ["telegram.org", "github.com"]  # Default allowed domains
            }
        if chat_id not in allowed_links:
            allowed_links[chat_id] = group_settings[chat_id]["allowed_domains"]
    
    # [Previous methods (start, button_handler, show_user_groups) remain the same...]
    
    def show_group_settings(self, query, group_id):
        self.initialize_group_settings(group_id)
        settings = group_settings[group_id]
        
        keyboard = [
            [
                InlineKeyboardButton(
                    f"{'✅' if settings['block_links'] else '❌'} Block Links",
                    callback_data=f"setting_{group_id}_block_links"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{'✅' if settings['block_forwards'] else '❌'} Block Forwards",
                    callback_data=f"setting_{group_id}_block_forwards"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{'✅' if settings['block_mentions'] else '❌'} Block Username Mentions",
                    callback_data=f"setting_{group_id}_block_mentions"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{'✅' if settings['warn_on_spam'] else '❌'} Warn on Violations",
                    callback_data=f"setting_{group_id}_warn_on_spam"
                )
            ],
            [
                InlineKeyboardButton(
                    f"{'✅' if settings['auto_mute'] else '❌'} Auto Mute ({settings['max_warnings']} warns)",
                    callback_data=f"setting_{group_id}_auto_mute"
                )
            ],
            [
                InlineKeyboardButton(
                    f"⏱ Mute Duration: {settings['mute_duration']}",
                    callback_data=f"duration_{group_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔗 Manage Allowed Links",
                    callback_data=f"links_{group_id}"
                )
            ],
            [InlineKeyboardButton("🔙 Back to Groups", callback_data="your_groups")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(
            f"⚙️ Group Settings\n\n"
            f"Configure moderation rules for this group:",
            reply_markup=reply_markup
        )
    
    def toggle_group_setting(self, query, group_id, setting):
        self.initialize_group_settings(group_id)
        group_settings[group_id][setting] = not group_settings[group_id][setting]
        self.show_group_settings(query, group_id)
    
    def manage_allowed_links(self, query, group_id):
        self.initialize_group_settings(group_id)
        domains = "\n".join(allowed_links.get(group_id, []))
        
        keyboard = [
            [InlineKeyboardButton("➕ Add Allowed Domain", callback_data=f"addlink_{group_id}")],
            [InlineKeyboardButton("➖ Remove Allowed Domain", callback_data=f"removelink_{group_id}")],
            [InlineKeyboardButton("🔙 Back to Settings", callback_data=f"group_{group_id}")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(
            f"🔗 Allowed Links for This Group:\n\n"
            f"{domains if domains else 'No allowed domains configured'}",
            reply_markup=reply_markup
        )
    
    def allow_link(self, update: Update, context: CallbackContext):
        if not context.args:
            update.message.reply_text("Please specify a domain to allow (without http://)\nExample: /allowlink example.com")
            return
            
        domain = context.args[0].lower().replace("http://", "").replace("https://", "").split("/")[0]
        chat_id = str(update.message.chat_id)
        
        self.initialize_group_settings(chat_id)
        if domain not in allowed_links[chat_id]:
            allowed_links[chat_id].append(domain)
            group_settings[chat_id]["allowed_domains"] = allowed_links[chat_id]
            update.message.reply_text(f"✅ Domain {domain} added to allowed list")
        else:
            update.message.reply_text(f"ℹ️ Domain {domain} is already allowed")
    
    def block_link(self, update: Update, context: CallbackContext):
        if not context.args:
            update.message.reply_text("Please specify a domain to block\nExample: /blocklink example.com")
            return
            
        domain = context.args[0].lower()
        chat_id = str(update.message.chat_id)
        
        self.initialize_group_settings(chat_id)
        if domain in allowed_links[chat_id]:
            allowed_links[chat_id].remove(domain)
            group_settings[chat_id]["allowed_domains"] = allowed_links[chat_id]
            update.message.reply_text(f"✅ Domain {domain} removed from allowed list")
        else:
            update.message.reply_text(f"ℹ️ Domain {domain} wasn't in allowed list")
    
    def message_filter(self, update: Update, context: CallbackContext):
        message = update.message
        chat_id = str(message.chat_id)
        user = message.from_user
        
        # Skip if no settings exist or user is admin
        if chat_id not in group_settings or self.is_admin(update, user.id):
            return
        
        self.initialize_group_settings(chat_id)
        settings = group_settings[chat_id]
        
        # Check for username mentions (@username)
        if settings.get("block_mentions", False) and message.entities:
            for entity in message.entities:
                if entity.type == "mention":
                    message.delete()
                    if settings.get("warn_on_spam", True):
                        self.warn_user_auto(update, context, "mentioning usernames")
                    return
        
        # Check for links
        if settings.get("block_links", True) and message.entities:
            for entity in message.entities:
                if entity.type in ["url", "text_link"]:
                    url = message.text[entity.offset:entity.offset + entity.length] if entity.type == "url" else entity.url
                    if not self.is_allowed_link(chat_id, url):
                        message.delete()
                        if settings.get("warn_on_spam", True):
                            self.warn_user_auto(update, context, "sharing links")
                        return
        
        # Check for forwarded messages
        if settings.get("block_forwards", True) and (message.forward_from or message.forward_from_chat):
            message.delete()
            if settings.get("warn_on_spam", True):
                self.warn_user_auto(update, context, "forwarding messages")
            return
    
    def is_allowed_link(self, chat_id, url):
        """Check if a link is in the allowed list"""
        if chat_id not in allowed_links:
            return False
        
        domain = re.sub(r'^https?://(www\.)?', '', url.lower()).split('/')[0]
        return any(allowed_domain in domain for allowed_domain in allowed_links[chat_id])
    
    def warn_user_auto(self, update: Update, context: CallbackContext, reason: str):
        user = update.message.from_user
        chat_id = str(update.message.chat_id)
        
        self.initialize_group_settings(chat_id)
        
        if chat_id not in user_warnings:
            user_warnings[chat_id] = {}
            
        if user.id not in user_warnings[chat_id]:
            user_warnings[chat_id][user.id] = 0
            
        user_warnings[chat_id][user.id] += 1
        
        settings = group_settings[chat_id]
        max_warnings = settings.get("max_warnings", 3)
        
        warning_msg = (
            f"⚠️ Auto-warning: {user.name} warned for {reason}.\n"
            f"Total warnings: {user_warnings[chat_id][user.id]}/{max_warnings}"
        )
        
        if settings.get("auto_mute", True) and user_warnings[chat_id][user.id] >= max_warnings:
            mute_duration = self.parse_duration(settings.get("mute_duration", "1d"))
            self.mute_user_auto(update, context, mute_duration)
            warning_msg += (
                f"\n🔇 Action: User has been muted automatically "
                f"for {self.format_duration(mute_duration)} (reached {max_warnings} warnings)"
            )
            user_warnings[chat_id][user.id] = 0  # Reset warnings after mute
        
        context.bot.send_message(chat_id=chat_id, text=warning_msg)
    
    def mute_user_auto(self, update: Update, context: CallbackContext, duration: timedelta):
        user = update.message.from_user
        chat_id = update.message.chat_id
        
        try:
            permissions = ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False
            )
            
            until_date = datetime.now(pytz.utc) + duration
            context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user.id,
                permissions=permissions,
                until_date=until_date
            )
        except Exception as e:
            logger.error(f"Error muting user: {str(e)}")

    # [Previous helper methods (is_admin, parse_duration, format_duration) remain the same...]

if __name__ == '__main__':
    TOKEN = "8017193630:AAFaMRpJ7Hk-2MTibaWOR_71-NYuFgr_2_U"
    bot = EnhancedGroupBot(TOKEN)
    bot.updater.start_polling()
    bot.updater.idle()
