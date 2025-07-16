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

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Simulated databases (in-memory dicts)
group_settings = {}
user_warnings = {}
allowed_links = {}
action_settings = {}

def parse_duration(duration_str):
    """
    Parses duration strings like '1h', '30m', '2d' into timedelta.
    """
    number = int(re.findall(r'\d+', duration_str)[0])
    if 'h' in duration_str:
        return timedelta(hours=number)
    elif 'm' in duration_str:
        return timedelta(minutes=number)
    elif 'd' in duration_str:
        return timedelta(days=number)
    else:
        return timedelta(hours=1)  # default 1 hour

class UltimateGroupBot:
    def __init__(self, token):
        self.updater = Updater(token, use_context=True)
        self.dispatcher = self.updater.dispatcher

        # Register handlers
        self.dispatcher.add_handler(CommandHandler("start", self.start))
        self.dispatcher.add_handler(CommandHandler("settings", self.group_settings_command))
        self.dispatcher.add_handler(CommandHandler("help", self.show_help))
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

    def initialize_group_settings(self, group_id):
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

    def start(self, update: Update, context: CallbackContext):
        if update.message.chat.type == "private":
            keyboard = [
                [InlineKeyboardButton("➕ Add me to Group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
                [InlineKeyboardButton("📊 Your Groups", callback_data="your_groups")],
                [InlineKeyboardButton("📢 Your Channels", callback_data="your_channels")],
                [InlineKeyboardButton("❓ Help", callback_data="help_command")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            update.message.reply_text(
                "👋 Welcome to Ultimate Group Manager Bot!\n\n"
                "🔹 Add me to your group/channel\n"
                "🔹 Configure group settings\n"
                "🔹 Powerful moderation tools",
                reply_markup=reply_markup
            )
        else:
            self.show_help(update, context)

    def show_help(self, update: Update, context: CallbackContext):
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
        update.message.reply_text(help_text, parse_mode="Markdown")

    def group_settings_command(self, update: Update, context: CallbackContext):
        chat = update.message.chat
        group_id = str(chat.id)
        if chat.type == "channel":
            self.show_channel_settings(update, group_id)
        else:
            self.show_group_settings(update, group_id)

    def show_group_settings(self, update_or_query, group_id):
        self.initialize_group_settings(group_id)
        settings = group_settings[group_id]

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
            update_or_query.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            update_or_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

    def show_channel_settings(self, update_or_query, channel_id):
        self.initialize_group_settings(channel_id)

        keyboard = [
            [InlineKeyboardButton("↩️ Remove Forward Tag", callback_data=f"channel_fwd_{channel_id}")],
            [InlineKeyboardButton("🔙 Back", callback_data="your_channels")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        text = "📢 *Channel Settings*\n\nConfigure forwarding behavior:"

        if isinstance(update_or_query, Update):
            update_or_query.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            update_or_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

    def show_link_settings(self, query, group_id):
        self.initialize_group_settings(group_id)
        settings = group_settings[group_id]
        actions = action_settings.get(group_id, {}).get("links", {})

        keyboard = [
            [InlineKeyboardButton(
                f"{'✅' if settings['block_links'] else '❌'} Block Links",
                callback_data=f"toggle_block_links_{group_id}"
            )],
            [InlineKeyboardButton(
                "✏️ Edit Allowed Domains",
                callback_data=f"edit_links_{group_id}"
            )],
            [InlineKeyboardButton(
                "⚡ Action: " + actions.get("action", "Delete"),
                callback_data=f"link_action_{group_id}"
            )],
            [InlineKeyboardButton(
                f"⏱ Duration: {actions.get('duration', '1h')}",
                callback_data=f"link_duration_{group_id}"
            )],
            [InlineKeyboardButton(
                f"⚠️ Warn: {'Yes' if actions.get('warn', True) else 'No'}",
                callback_data=f"link_warn_{group_id}"
            )],
            [InlineKeyboardButton("🔙 Back", callback_data=f"group_{group_id}")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(
            "🔗 *Link Settings*\n\nConfigure how to handle links:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

    # Placeholder for mention, forward, warning settings views - you can expand similarly

    def button_handler(self, update: Update, context: CallbackContext):
        query = update.callback_query
        query.answer()

        data = query.data
        if data == "your_groups":
            self.show_user_groups(query)
        elif data == "your_channels":
            self.show_user_channels(query)
        elif data == "help_command":
            self.show_help(query, context)
        elif data.startswith("group_"):
            group_id = data.split("_")[1]
            self.show_group_settings(query, group_id)
        elif data.startswith("channel_"):
            channel_id = data.split("_")[1]
            self.show_channel_settings(query, channel_id)
        elif data.startswith("link_settings_"):
            group_id = data.split("_")[2]
            self.show_link_settings(query, group_id)
        # Add more button callbacks as needed

    def message_filter(self, update: Update, context: CallbackContext):
        message = update.message
        chat_id = str(message.chat_id)
        self.initialize_group_settings(chat_id)

        # Only process groups/supergroups
        if message.chat.type not in ['group', 'supergroup']:
            return

        # Check for forwarded messages block
        if message.forward_date and group_settings[chat_id].get("block_forwards", False):
            self.handle_violation(update, context, "forward")
            return

        # Check for blocked links
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
                        self.handle_violation(update, context, "links")
                        break

    def handle_violation(self, update: Update, context: CallbackContext, violation_type):
        chat_id = str(update.message.chat_id)
        user_id = update.message.from_user.id
        actions = action_settings.get(chat_id, {}).get(violation_type, {})

        # Delete message if configured
        if actions.get("delete", True):
            try:
                update.message.delete()
            except Exception as e:
                logger.warning(f"Failed to delete message: {e}")

        # Warn user if configured
        if actions.get("warn", True):
            self.warn_user(update, context)

        # Take additional action if configured
        action = actions.get("action")
        duration = parse_duration(actions.get("duration", "1h"))

        if action == "mute":
            self.mute_user_with_duration(update, context, duration)
        elif action == "ban":
            self.ban_user_with_duration(update, context, duration)

    def warn_user(self, update: Update, context: CallbackContext):
        chat_id = str(update.message.chat_id)
        user_id = update.message.from_user.id

        self.initialize_group_settings(chat_id)
        if chat_id not in user_warnings:
            user_warnings[chat_id] = {}

        warns = user_warnings[chat_id].get(user_id, 0) + 1
        user_warnings[chat_id][user_id] = warns

        update.message.reply_text(f"⚠️ User {update.message.from_user.first_name} warned! Total warnings: {warns}")

        # Example: Auto ban after 3 warnings
        if warns >= 3:
            update.message.reply_text(f"🚫 User {update.message.from_user.first_name} banned for exceeding warnings.")
            try:
                context.bot.kick_chat_member(chat_id=int(chat_id), user_id=user_id)
                user_warnings[chat_id][user_id] = 0  # reset after ban
            except Exception as e:
                update.message.reply_text(f"Failed to ban user: {e}")

    def ban_user(self, update: Update, context: CallbackContext):
        if not update.message.reply_to_message:
            update.message.reply_text("❗️ Please reply to the user you want to ban.")
            return
        chat_id = update.message.chat_id
        user_id = update.message.reply_to_message.from_user.id
        try:
            context.bot.kick_chat_member(chat_id=chat_id, user_id=user_id)
            update.message.reply_text("User has been banned.")
        except Exception as e:
            update.message.reply_text(f"Failed to ban user: {e}")

    def unban_user(self, update: Update, context: CallbackContext):
        if not update.message.reply_to_message:
            update.message.reply_text("❗️ Please reply to the user you want to unban.")
            return
        chat_id = update.message.chat_id
        user_id = update.message.reply_to_message.from_user.id
        try:
            context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
            update.message.reply_text("User has been unbanned.")
        except Exception as e:
            update.message.reply_text(f"Failed to unban user: {e}")

    def mute_user(self, update: Update, context: CallbackContext):
        if not update.message.reply_to_message:
            update.message.reply_text("❗️ Please reply to the user you want to mute.")
            return
        chat_id = update.message.chat_id
        user_id = update.message.reply_to_message.from_user.id
        try:
            context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False)
            )
            update.message.reply_text("User has been muted.")
        except Exception as e:
            update.message.reply_text(f"Failed to mute user: {e}")

    def unmute_user(self, update: Update, context: CallbackContext):
        if not update.message.reply_to_message:
            update.message.reply_text("❗️ Please reply to the user you want to unmute.")
            return
        chat_id = update.message.chat_id
        user_id = update.message.reply_to_message.from_user.id
        try:
            context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True
                )
            )
            update.message.reply_text("User has been unmuted.")
        except Exception as e:
            update.message.reply_text(f"Failed to unmute user: {e}")

    def mute_user_with_duration(self, update: Update, context: CallbackContext, duration: timedelta):
        if not update.message.reply_to_message:
            update.message.reply_text("❗️ Please reply to the user you want to mute.")
            return
        chat_id = update.message.chat_id
        user_id = update.message.reply_to_message.from_user.id
        until_date = datetime.utcnow() + duration
        try:
            context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date
            )
            update.message.reply_text(f"User muted for {duration}.")
        except Exception as e:
            update.message.reply_text(f"Failed to mute user: {e}")

    def ban_user_with_duration(self, update: Update, context: CallbackContext, duration: timedelta):
        if not update.message.reply_to_message:
            update.message.reply_text("❗️ Please reply to the user you want to ban.")
            return
        chat_id = update.message.chat_id
        user_id = update.message.reply_to_message.from_user.id
        until_date = datetime.utcnow() + duration
        try:
            context.bot.kick_chat_member(chat_id=chat_id, user_id=user_id, until_date=until_date)
            update.message.reply_text(f"User banned for {duration}.")
        except Exception as e:
            update.message.reply_text(f"Failed to ban user: {e}")

    def allow_link(self, update: Update, context: CallbackContext):
        chat_id = str(update.message.chat_id)
        self.initialize_group_settings(chat_id)
        if len(context.args) == 0:
            update.message.reply_text("Please specify a domain to allow, e.g. /allowlink example.com")
            return
        domain = context.args[0].lower()
        group_settings[chat_id]["allowed_domains"].add(domain)
        update.message.reply_text(f"Allowed domain added: {domain}")

    def block_link(self, update: Update, context: CallbackContext):
        chat_id = str(update.message.chat_id)
        self.initialize_group_settings(chat_id)
        if len(context.args) == 0:
            update.message.reply_text("Please specify a domain to block, e.g. /blocklink example.com")
            return
        domain = context.args[0].lower()
        if domain in group_settings[chat_id]["allowed_domains"]:
            group_settings[chat_id]["allowed_domains"].remove(domain)
            update.message.reply_text(f"Allowed domain removed: {domain}")
        else:
            update.message.reply_text(f"Domain was not in allowed list: {domain}")

    def show_user_groups(self, query):
        # This should show groups where user is admin or the bot is admin; here dummy example
        keyboard = [
            [InlineKeyboardButton("Group 1", callback_data="group_12345")],
            [InlineKeyboardButton("Group 2", callback_data="group_67890")],
            [InlineKeyboardButton("🔙 Back", callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("📊 *Your Groups*\n\nSelect a group to configure:", reply_markup=reply_markup, parse_mode="Markdown")

    def show_user_channels(self, query):
        # Dummy example
        keyboard = [
            [InlineKeyboardButton("Channel 1", callback_data="channel_11111")],
            [InlineKeyboardButton("Channel 2", callback_data="channel_22222")],
            [InlineKeyboardButton("🔙 Back", callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("📢 *Your Channels*\n\nSelect a channel to configure:", reply_markup=reply_markup, parse_mode="Markdown")

if __name__ == '__main__':
    TOKEN = "8017193630:AAFaMRpJ7Hk-2MTibaWOR_71-NYuFgr_2_U"
