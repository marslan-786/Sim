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

# Database simulation
group_settings = {}
user_warnings = {}
allowed_links = {}

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

    def start(self, update: Update, context: CallbackContext):
        if update.message.chat.type == "private":
            keyboard = [
                [InlineKeyboardButton("➕ Add me to Group", url="https://t.me/yourbot?startgroup=true")],
                [InlineKeyboardButton("📊 Your Groups", callback_data="your_groups")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            update.message.reply_text(
                "👋 Welcome to Group Manager Bot!\n\n"
                "🔹 Add me to your group\n"
                "🔹 Configure group settings",
                reply_markup=reply_markup
            )
        else:
            update.message.reply_text("ℹ️ I'm active in this group! Use /settings to configure.")

    def group_settings_command(self, update: Update, context: CallbackContext):
        self.show_group_settings(update, str(update.message.chat_id))

    def button_handler(self, update: Update, context: CallbackContext):
        query = update.callback_query
        query.answer()

        if query.data == "your_groups":
            self.show_user_groups(query)
        elif query.data.startswith("group_"):
            group_id = query.data.split("_")[1]
            self.show_group_settings(query, group_id)
        elif query.data.startswith("setting_"):
            group_id, setting = query.data.split("_")[1:]
            self.toggle_group_setting(query, group_id, setting)
        elif query.data.startswith("duration_"):
            group_id = query.data.split("_")[1]
            self.change_mute_duration(query, group_id)
        elif query.data.startswith("links_"):
            group_id = query.data.split("_")[1]
            self.manage_allowed_links(query, group_id)
        elif query.data == "back_to_groups":
            self.show_user_groups(query)

    def show_user_groups(self, query):
        groups = [{"id": "-100123456789", "title": "Test Group"}]
        keyboard = [[InlineKeyboardButton(group["title"], callback_data=f"group_{group['id']}")] for group in groups]
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="start")])
        query.edit_message_text("📋 Your Groups:", reply_markup=InlineKeyboardMarkup(keyboard))

    def initialize_group_settings(self, chat_id):
        if chat_id not in group_settings:
            group_settings[chat_id] = {
                "block_links": True,
                "block_forwards": True,
                "block_mentions": False,
                "warn_on_spam": True,
                "auto_mute": True,
                "mute_duration": "1d",
                "max_warnings": 3,
                "allowed_domains": ["telegram.org", "github.com"]
            }
        if chat_id not in allowed_links:
            allowed_links[chat_id] = group_settings[chat_id]["allowed_domains"]

    def show_group_settings(self, update_or_query, group_id):
        self.initialize_group_settings(group_id)
        settings = group_settings[group_id]

        keyboard = [
            [InlineKeyboardButton(f"{'✅' if settings['block_links'] else '❌'} Block Links", callback_data=f"setting_{group_id}_block_links")],
            [InlineKeyboardButton(f"{'✅' if settings['block_forwards'] else '❌'} Block Forwards", callback_data=f"setting_{group_id}_block_forwards")],
            [InlineKeyboardButton(f"{'✅' if settings['block_mentions'] else '❌'} Block Mentions", callback_data=f"setting_{group_id}_block_mentions")],
            [InlineKeyboardButton(f"{'✅' if settings['warn_on_spam'] else '❌'} Warn on Violations", callback_data=f"setting_{group_id}_warn_on_spam")],
            [InlineKeyboardButton(f"{'✅' if settings['auto_mute'] else '❌'} Auto Mute ({settings['max_warnings']} warns)", callback_data=f"setting_{group_id}_auto_mute")],
            [InlineKeyboardButton(f"⏱ Mute Duration: {settings['mute_duration']}", callback_data=f"duration_{group_id}")],
            [InlineKeyboardButton("🔗 Manage Allowed Links", callback_data=f"links_{group_id}")],
            [InlineKeyboardButton("🔙 Back to Groups", callback_data="your_groups")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        text = "⚙️ Group Settings\n\nConfigure moderation rules for this group:"

        if isinstance(update_or_query, Update):
            update_or_query.message.reply_text(text, reply_markup=reply_markup)
        else:
            update_or_query.edit_message_text(text, reply_markup=reply_markup)

    def ban_user(self, update: Update, context: CallbackContext):
        if update.message.reply_to_message:
            user_id = update.message.reply_to_message.from_user.id
            context.bot.kick_chat_member(update.message.chat_id, user_id)
            update.message.reply_text("🚫 User has been banned.")
        else:
            update.message.reply_text("⚠️ Reply to a user's message to ban them.")

    def unban_user(self, update: Update, context: CallbackContext):
        if update.message.reply_to_message:
            user_id = update.message.reply_to_message.from_user.id
            context.bot.unban_chat_member(update.message.chat_id, user_id)
            update.message.reply_text("✅ User has been unbanned.")
        else:
            update.message.reply_text("⚠️ Reply to a user's message to unban them.")

    def mute_user(self, update: Update, context: CallbackContext):
        if update.message.reply_to_message:
            user_id = update.message.reply_to_message.from_user.id
            until_date = datetime.now() + timedelta(days=1)
            context.bot.restrict_chat_member(update.message.chat_id, user_id, ChatPermissions(can_send_messages=False), until_date)
            update.message.reply_text("🔇 User muted for 1 day.")
        else:
            update.message.reply_text("⚠️ Reply to a user's message to mute them.")

    def unmute_user(self, update: Update, context: CallbackContext):
        if update.message.reply_to_message:
            user_id = update.message.reply_to_message.from_user.id
            context.bot.restrict_chat_member(update.message.chat_id, user_id, ChatPermissions(can_send_messages=True))
            update.message.reply_text("🔊 User has been unmuted.")
        else:
            update.message.reply_text("⚠️ Reply to a user's message to unmute them.")

    def warn_user(self, update: Update, context: CallbackContext):
        if update.message.reply_to_message:
            user_id = update.message.reply_to_message.from_user.id
            chat_id = str(update.message.chat_id)
            self.initialize_group_settings(chat_id)
            user_warnings.setdefault(chat_id, {})
            user_warnings[chat_id].setdefault(user_id, 0)
            user_warnings[chat_id][user_id] += 1
            count = user_warnings[chat_id][user_id]
            max_warn = group_settings[chat_id]["max_warnings"]
            update.message.reply_text(f"⚠️ Warned! ({count}/{max_warn})")

            if count >= max_warn and group_settings[chat_id]["auto_mute"]:
                self.mute_user(update, context)
        else:
            update.message.reply_text("⚠️ Reply to a user's message to warn them.")

    def allow_link(self, update: Update, context: CallbackContext):
        chat_id = str(update.message.chat_id)
        self.initialize_group_settings(chat_id)
        if context.args:
            domain = context.args[0]
            allowed_links[chat_id].append(domain)
            update.message.reply_text(f"✅ Allowed: {domain}")
        else:
            update.message.reply_text("Usage: /allowlink domain.com")

    def block_link(self, update: Update, context: CallbackContext):
        chat_id = str(update.message.chat_id)
        self.initialize_group_settings(chat_id)
        if context.args:
            domain = context.args[0]
            if domain in allowed_links[chat_id]:
                allowed_links[chat_id].remove(domain)
                update.message.reply_text(f"🚫 Blocked: {domain}")
            else:
                update.message.reply_text("Domain not in list.")
        else:
            update.message.reply_text("Usage: /blocklink domain.com")

    def change_mute_duration(self, query, group_id):
        durations = ["1h", "1d", "3d", "7d"]
        current = group_settings[group_id]["mute_duration"]
        next_index = (durations.index(current) + 1) % len(durations)
        group_settings[group_id]["mute_duration"] = durations[next_index]
        self.show_group_settings(query, group_id)

    def toggle_group_setting(self, query, group_id, setting):
        self.initialize_group_settings(group_id)
        group_settings[group_id][setting] = not group_settings[group_id][setting]
        self.show_group_settings(query, group_id)

    def manage_allowed_links(self, query, group_id):
        self.initialize_group_settings(group_id)
        links = allowed_links[group_id]
        text = "🔗 Allowed Domains:\n" + "\n".join(links)
        query.edit_message_text(text + "\n\nUse /allowlink and /blocklink to manage.")

    def message_filter(self, update: Update, context: CallbackContext):
        chat_id = str(update.message.chat_id)
        self.initialize_group_settings(chat_id)
        message = update.message
        text = message.text or ""
        user_id = message.from_user.id

        # Block forwards
        if message.forward_date and group_settings[chat_id]["block_forwards"]:
            message.delete()
            return

        # Block mentions
        if group_settings[chat_id]["block_mentions"] and "@" in text:
            message.delete()
            return

        # Block unauthorized links
        if group_settings[chat_id]["block_links"]:
            urls = re.findall(r"(https?://\S+)", text)
            for url in urls:
                if not any(domain in url for domain in allowed_links[chat_id]):
                    message.delete()
                    return

        # Detect spam
        repeated_chars = re.search(r"(.)\1{10,}", text)
        emojis = re.findall(r"[🌟✨🔥💥🚀💣😈🤖🤑]+", text)
        if repeated_chars or len(emojis) > 5:
            if group_settings[chat_id]["warn_on_spam"]:
                user_warnings.setdefault(chat_id, {})
                user_warnings[chat_id].setdefault(user_id, 0)
                user_warnings[chat_id][user_id] += 1
                message.reply_text(f"⚠️ Spam detected! Warning ({user_warnings[chat_id][user_id]})")
                if user_warnings[chat_id][user_id] >= group_settings[chat_id]["max_warnings"]:
                    self.mute_user(update, context)

if __name__ == '__main__':
    TOKEN = "8017193630:AAFaMRpJ7Hk-2MTibaWOR_71-NYuFgr_2_U"
    bot = EnhancedGroupBot(TOKEN)
    bot.updater.start_polling()
    bot.updater.idle()
