import logging
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes, ChatMemberHandler, filters, MessageHandler
from database import Database
import time
import os
from aiohttp import web
import ssl

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize database
db = Database()

# Your group ID (make sure it starts with -100 for supergroups)
GROUP_ID = int(os.environ.get('GROUP_ID', '-1002384613497'))

# Webhook settings
DOMAIN = os.environ.get('DOMAIN', 'bot.patoonsol.xyz').rstrip('/')  # Your Cloudflare domain
WEBHOOK_PATH = '/webhook'
WEBHOOK_URL = f"https://{DOMAIN}{WEBHOOK_PATH}"

# Port is given by Render
PORT = int(os.environ.get('PORT', '8080'))

# Telegram Bot Token
TOKEN = os.environ.get('BOT_TOKEN', '7790381038:AAE26s1oHYvlZX2wyY_cW7VsjJmNaxXFlYc')

async def track_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Track when users join or leave the group"""
    try:
        if not update.chat_member:
            return

        chat_id = update.chat_member.chat.id
        if chat_id != GROUP_ID:
            return

        new_member = update.chat_member.new_chat_member
        old_member = update.chat_member.old_chat_member
        
        if not new_member or not old_member:
            return

        user_id = new_member.user.id
        
        # Skip updates that don't represent actual status changes
        if new_member.status == old_member.status:
            logger.info(f"Skipping duplicate status update for user {user_id}")
            return
            
        logger.info(f"Member status change - User: {user_id}, Old: {old_member.status}, New: {new_member.status}")
        
        # Handle member leaving
        if new_member.status in ['left', 'kicked', 'banned'] and old_member.status == 'member':
            logger.info(f"User {user_id} left the group")
            success = await db.remove_user(user_id)
            if success:
                inviter_id = await db.get_inviter(user_id)
                if inviter_id:
                    active_referrals = await db.get_active_referrals(inviter_id)
                    await context.bot.send_message(
                        chat_id=inviter_id,
                        text=f"ℹ️ One of your referred users left the group.\nYou now have {active_referrals} active referrals.",
                        parse_mode='HTML'
                    )
            
        # Handle member joining
        elif new_member.status == 'member' and old_member.status in ['left', 'kicked', 'banned']:
            inviter_id = None
            invite_info = None

            # Try to get invite link information
            if hasattr(update.chat_member, 'invite_link') and update.chat_member.invite_link:
                invite_link = update.chat_member.invite_link
                logger.info(f"Invite link used: {invite_link.name}")
                
                if invite_link.name and invite_link.name.startswith('ref_'):
                    try:
                        inviter_id = int(invite_link.name.split('_')[1])
                        logger.info(f"Found inviter_id {inviter_id} from invite link {invite_link.name}")
                        invite_info = invite_link.name
                    except (IndexError, ValueError) as e:
                        logger.error(f"Error extracting inviter_id from invite link: {e}")
            
            if inviter_id and inviter_id != user_id:
                logger.info(f"Processing join for user {user_id} invited by {inviter_id}")
                # First ensure inviter exists in database
                await db.add_user(inviter_id)
                
                # Add new user with referrer
                success = await db.add_user(user_id, inviter_id)
                logger.info(f"Added user {user_id} with inviter {inviter_id}, success: {success}")
                
                if success:
                    active_referrals = await db.get_active_referrals(inviter_id)
                    logger.info(f"Inviter {inviter_id} now has {active_referrals} active referrals")
                    try:
                        inviter_msg = (
                            f"🎉 New referral! User {new_member.user.first_name} joined using your invite link!\n"
                            f"Your active referrals: {active_referrals} 🌟\n"
                            f"Invite link used: {invite_info}"
                        )
                        await context.bot.send_message(
                            chat_id=inviter_id,
                            text=inviter_msg,
                            parse_mode='HTML'
                        )
                        logger.info(f"Sent notification to inviter {inviter_id}")
                    except Exception as e:
                        logger.error(f"Could not send notification to inviter: {e}")
            else:
                # User joined without referral
                logger.info(f"User {user_id} joined without referral")
                await db.add_user(user_id)
                
    except Exception as e:
        logger.error(f"Error in track_chat_member: {e}", exc_info=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    chat_type = update.effective_chat.type

    if chat_type == 'private':
        try:
            # Check bot permissions
            try:
                # Get bot's member info
                bot_member = await context.bot.get_chat_member(GROUP_ID, context.bot.id)
                logger.info(f"Bot status in group: {bot_member.status}")
                
                if bot_member.status != 'administrator':
                    raise Exception("Bot must be an admin in the group")
                
                # Get chat info to verify group type
                chat = await context.bot.get_chat(GROUP_ID)
                if not chat.type in ['supergroup', 'group']:
                    raise Exception("Invalid group type. Must be a supergroup or group")

                # Try a test invite link to verify permissions
                test_link = None
                try:
                    test_link = await context.bot.create_chat_invite_link(
                        chat_id=GROUP_ID,
                        name="test_link",
                        creates_join_request=False,
                        expire_date=int(time.time()) + 30,  # 30 seconds expiry
                        member_limit=1
                    )
                    if test_link:
                        # If we got here, we have invite link permission
                        # Revoke the test link
                        await context.bot.revoke_chat_invite_link(GROUP_ID, test_link.invite_link)
                except Exception as e:
                    raise Exception("Bot cannot create invite links. Please check admin rights")

            except Exception as e:
                logger.error(f"Permission check failed: {e}")
                raise Exception(f"Permission check failed: {str(e)}")

            # Create actual invite link
            try:
                current_time = int(time.time())
                invite_link = await context.bot.create_chat_invite_link(
                    chat_id=GROUP_ID,
                    name=f"ref_{user_id}_{current_time}",
                    creates_join_request=False,
                    expire_date=None,
                    member_limit=None
                )
                logger.info(f"Successfully created invite link for user {user_id}")
            except Exception as e:
                logger.error(f"Error creating invite link: {e}")
                raise Exception(f"Failed to create invite link: {str(e)}")
            
            # Add user to database if not exists
            await db.add_user(user_id)
            
            welcome_msg = (
                "🎉 <b>Welcome to the Referral Program!</b> 🎉\n\n"
                f"📱 <b>Your unique invite link:</b>\n{invite_link.invite_link}\n\n"
                "🔥 Share this link to invite others to the group!\n\n"
                "📊 <b>Available Commands:</b>\n"
                "👉 /start - Get a new invite link\n"
                "👉 /leaderboard - View top inviters\n"
                "👉 /myreferrals - Check your referral count\n\n"
                "✨ <i>You'll get notified when someone joins using your link!</i>"
            )
            
            await update.message.reply_text(
                welcome_msg,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            
        except Exception as e:
            logger.error(f"Error in start command: {e}", exc_info=True)
            error_msg = (
                "❌ <b>Error!</b>\n\n"
                "Bot permissions check failed. Please ensure:\n"
                "1️⃣ Bot is an admin in the group\n"
                "2️⃣ Bot has these admin rights enabled:\n"
                "   • Can invite users via link\n"
                "   • Can manage group\n\n"
                f"Error details: {str(e)}"
            )
            await update.message.reply_text(
                error_msg,
                parse_mode='HTML'
            )
    else:
        bot_username = context.bot.username
        await update.message.reply_text(
            f"📱 <b>Get your referral link in private!</b>\n"
            f"👉 <a href='https://t.me/{bot_username}?start'>Click here to start</a>",
            parse_mode='HTML',
            disable_web_page_preview=True
        )

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show top 10 inviters"""
    try:
        top_inviters = await db.get_leaderboard(limit=10)  # Explicitly set limit to 10
        
        if not top_inviters:
            await update.message.reply_text("🏆 No referrals yet! Be the first to invite someone! 🎯")
            return

        leaderboard_text = "🏆 <b>Top 10 Inviters</b> 🏆\n\n"
        for rank, (user_id, referrals) in enumerate(top_inviters, 1):
            # Special medals for top 3
            medal = {
                1: "🥇", 
                2: "🥈", 
                3: "🥉"
            }.get(rank, f"{rank}.")

            try:
                user = await context.bot.get_chat(user_id)
                name = user.username or user.first_name or str(user_id)
                name = f"@{name}" if user.username else name
                
                # Add stars based on referral count
                stars = "⭐" * min(5, referrals)  # Max 5 stars
                
                leaderboard_text += (
                    f"{medal} {name}\n"
                    f"└ {referrals} referrals {stars}\n\n"
                )
            except Exception as e:
                logger.error(f"Error getting user info for {user_id}: {e}")
                leaderboard_text += f"{medal} User {user_id}: {referrals} referrals\n\n"

        footer = (
            "ℹ️ <i>Invite more members to climb the leaderboard!\n"
            "Use /start to get your referral link</i>"
        )
        await update.message.reply_text(
            f"{leaderboard_text}\n{footer}",
            parse_mode='HTML',
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error showing leaderboard: {e}", exc_info=True)
        await update.message.reply_text("❌ Error fetching leaderboard. Please try again later.")

async def my_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's referral stats"""
    try:
        user_id = update.effective_user.id
        total_refs = await db.get_total_referrals(user_id)
        active_refs = await db.get_active_referrals(user_id)
        
        stats_text = (
            "📊 <b>Your Referral Stats</b>\n\n"
            f"👥 Total Referrals: {total_refs}\n"
            f"✅ Active Referrals: {active_refs}\n\n"
            "Use /start to get a new invite link!"
        )
        
        await update.message.reply_text(stats_text, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error showing referral stats: {e}", exc_info=True)
        await update.message.reply_text("❌ Error fetching your stats. Please try again later.")

async def setup_webhook(application: Application) -> None:
    webhook_info = await application.bot.get_webhook_info()
    
    # Detailed debug information
    logger.info("=== Webhook Debug Info ===")
    logger.info(f"DOMAIN env var: {os.environ.get('DOMAIN', 'not set')}")
    logger.info(f"Current webhook URL: {webhook_info.url}")
    logger.info(f"Attempting to set webhook URL: {WEBHOOK_URL}")
    logger.info(f"Bot username: {(await application.bot.get_me()).username}")
    logger.info("========================")
    
    # Test the webhook URL
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(WEBHOOK_URL) as response:
                logger.info(f"Webhook URL test status: {response.status}")
    except Exception as e:
        logger.error(f"Failed to test webhook URL: {str(e)}")
    
    # Only set webhook if it's not already set correctly
    if webhook_info.url != WEBHOOK_URL:
        logger.info(f"Setting webhook to {WEBHOOK_URL}")
        try:
            # Try to delete existing webhook first
            await application.bot.delete_webhook()
            logger.info("Deleted existing webhook")
            
            # Set new webhook
            await application.bot.set_webhook(
                url=WEBHOOK_URL,
                allowed_updates=['message', 'chat_member', 'callback_query'],
                secret_token=os.environ.get('WEBHOOK_SECRET', 'your-secret-token')
            )
            logger.info("Webhook set successfully")
            
            # Verify webhook was set
            new_webhook_info = await application.bot.get_webhook_info()
            logger.info(f"New webhook URL: {new_webhook_info.url}")
            
        except Exception as e:
            logger.error(f"Failed to set webhook: {str(e)}", exc_info=True)
    else:
        logger.info("Webhook already set correctly")

async def main():
    application = None
    runner = None
    try:
        # Initialize database first
        logger.info("Initializing database...")
        await db.init_db()
        logger.info("Database initialized successfully")

        # Get and display server IP
        try:
            import socket
            hostname = socket.gethostname()
            ip_address = socket.gethostbyname(hostname)
            logger.info(f"Server hostname: {hostname}")
            logger.info(f"Server IP address: {ip_address}")
        except Exception as e:
            logger.error(f"Failed to get IP address: {e}")

        # Initialize bot
        application = Application.builder().token(TOKEN).build()

        # Add command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("leaderboard", leaderboard))
        application.add_handler(CommandHandler("myreferrals", my_referrals))
        
        # Add chat member handler with high priority (group=1)
        application.add_handler(ChatMemberHandler(track_chat_member, ChatMemberHandler.CHAT_MEMBER), group=1)

        # Initialize the application
        await application.initialize()
        
        # Set up webhook
        await setup_webhook(application)
        
        # Start web application
        app = web.Application()
        
        # Handle webhook calls
        async def handle_webhook(request):
            try:
                # Log request information
                logger.info("Received webhook request")
                logger.info(f"Request headers: {dict(request.headers)}")
                
                # Get the request data
                json_data = await request.json()
                logger.info(f"Request data: {json_data}")
                
                # Verify webhook secret
                secret_header = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
                if secret_header != os.environ.get('WEBHOOK_SECRET', 'your-secret-token'):
                    logger.warning(f"Invalid webhook secret token. Expected: {os.environ.get('WEBHOOK_SECRET')}, Got: {secret_header}")
                    return web.Response(status=403)
                
                # Create update object
                update = Update.de_json(json_data, application.bot)
                if update:
                    logger.info(f"Successfully created Update object: {update}")
                    await application.process_update(update)
                    logger.info("Successfully processed update")
                    return web.Response()
                else:
                    logger.error("Failed to create Update object from data")
                    return web.Response(status=400)
                    
            except Exception as e:
                logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
                return web.Response(status=500)

        # Add routes
        app.router.add_post(WEBHOOK_PATH, handle_webhook)
        app.router.add_get("/", lambda r: web.Response(text="Bot is running"))
        
        # Start web server
        logger.info(f"Starting webhook server on port {PORT}")
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', PORT)
        await site.start()
        
        # Start the application
        await application.start()
        
        logger.info("Bot started successfully!")
        
        # Keep the app running
        while True:
            await asyncio.sleep(3600)  # Sleep for 1 hour
            
    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)
    finally:
        # Cleanup
        logger.info("Cleaning up...")
        if application:
            await application.stop()
        if runner:
            await runner.cleanup()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
