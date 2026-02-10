"""
Token management handlers.
Handles Upstox token checking, refreshing and authorization flow.
"""
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from telegram_bot.bot_controller import WAITING_AUTH_CODE
from telegram_bot.bot_controller.handlers_menu import is_authorized
from telegram_bot.token_manager import get_token_manager


async def handle_token_menu(query):
    """Handle token_menu callback"""
    token_manager = get_token_manager()
    token_info = token_manager.get_token_info()

    status_icon = "✅" if token_info['is_valid'] else "❌"
    msg = f"🔑 <b>Upstox Token Status</b>\n\n"
    msg += f"Status: {status_icon} {token_info['message']}\n"
    msg += f"Last Checked: {token_info['checked_at']}\n\n"

    if not token_info['is_valid']:
        msg += "⚠️ <b>Token needs refresh!</b>\n"
        msg += "Click 'Check Token' to verify or 'Refresh Token' to update.\n"

    keyboard = [
        [
            InlineKeyboardButton("🔄 Check Token", callback_data="check_token"),
            InlineKeyboardButton("🔑 Refresh Token", callback_data="refresh_token")
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def handle_check_token(query):
    """Handle check_token callback"""
    token_manager = get_token_manager()
    is_valid, message = token_manager.check_token_validity()

    status_icon = "✅" if is_valid else "❌"
    msg = f"🔑 <b>Token Check Result</b>\n\n"
    msg += f"{status_icon} {message}\n\n"
    msg += f"Checked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="token_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def handle_refresh_token(query):
    """Handle refresh_token callback"""
    token_manager = get_token_manager()
    auth_url = token_manager.get_authorization_url()

    if not auth_url:
        msg = "❌ <b>Error</b>\n\nMissing Upstox credentials in .env file."
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="token_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        return

    # Create clickable button with the auth URL
    keyboard = [
        [InlineKeyboardButton("🔐 Login to Upstox", url=auth_url)],
        [InlineKeyboardButton("✅ I've Authorized", callback_data="auth_complete")],
        [InlineKeyboardButton("🔙 Cancel", callback_data="token_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = (
        "🔑 <b>Token Refresh Process</b>\n\n"
        "<b>Step 1:</b> Click the 'Login to Upstox' button below\n"
        "<b>Step 2:</b> Enter OTP and authorize the app\n"
        "<b>Step 3:</b> Copy the authorization code from the redirect URL\n"
        "<b>Step 4:</b> Click 'I've Authorized' and paste the code\n\n"
        "The redirect URL will look like:\n"
        "<code>http://your-redirect-uri/?code=XXXXX</code>\n\n"
        "Copy only the code part (after <code>code=</code>)"
    )

    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def handle_auth_complete(query):
    """Handle auth_complete callback"""
    msg = (
        "📝 <b>Enter Authorization Code</b>\n\n"
        "Please send the authorization code you received from the redirect URL.\n\n"
        "Example: If the URL is:\n"
        "<code>http://localhost/?code=abc123xyz</code>\n\n"
        "Send: <code>abc123xyz</code>\n\n"
        "Or send /cancel to abort."
    )
    await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
    return WAITING_AUTH_CODE


async def refresh_token_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trigger token refresh process via /refresh_token command"""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("❌ Not authorized")
        return

    token_manager = get_token_manager()
    auth_url = token_manager.get_authorization_url()

    if not auth_url:
        await update.message.reply_text(
            "❌ <b>Error</b>\n\nMissing Upstox credentials in .env file.",
            parse_mode=ParseMode.HTML
        )
        return

    keyboard = [[InlineKeyboardButton("🔐 Login to Upstox", url=auth_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🔑 <b>Token Refresh</b>\n\n"
        "Click the button below to login to Upstox in your browser.\n\n"
        "After authorizing, copy the code from the redirect URL and send it back here.",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def handle_auth_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle authorization code submission"""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("❌ Not authorized")
        return ConversationHandler.END

    auth_code = update.message.text.strip()

    await update.message.reply_text(
        "🔄 <b>Processing...</b>\n\nExchanging code for access token...",
        parse_mode=ParseMode.HTML
    )

    token_manager = get_token_manager()
    success, message, token = token_manager.exchange_code_for_token(auth_code)

    if success:
        await update.message.reply_text(
            f"✅ <b>Success!</b>\n\n{message}\n\n"
            f"Your Upstox access token has been updated.\n\n"
            f"Use /menu to return to main menu.",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            f"❌ <b>Failed</b>\n\n{message}\n\n"
            f"Please try again with /refresh_token",
            parse_mode=ParseMode.HTML
        )

    return ConversationHandler.END
