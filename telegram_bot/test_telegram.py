"""
Test Telegram Integration
Sends a test message to verify bot configuration
"""
import os
import sys

from dotenv import load_dotenv

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

from telegram_alerts import format_signal_message, send_telegram_alert


def test_basic_message():
    """Test sending a basic message"""
    print("Testing basic Telegram message...")
    
    test_message = (
        "✅ *Test Message*\n\n"
        "Your Stock Advanced Bot is configured correctly!\n"
        "You should see this message in your Telegram chat."
    )
    
    success = send_telegram_alert(test_message)
    
    if success:
        print("✅ Test message sent successfully!")
        print("Check your Telegram to confirm.")
    else:
        print("❌ Failed to send test message.")
        print("Please check:")
        print("  1. TELEGRAM_BOT_TOKEN is correct")
        print("  2. TELEGRAM_CHAT_IDS are correct")
        print("  3. You've sent at least one message to your bot")
    
    return success


def test_signal_message():
    """Test sending a trading signal message"""
    print("\nTesting trading signal message...")
    
    # Mock signal data
    test_signal = {
        "signal": "BUY",
        "entry_price": 1245.50,
        "sl": 1230.25,
        "tp": 1269.90,
        "rr": 1.6
    }
    
    message = format_signal_message("INE467B01029", test_signal)
    success = send_telegram_alert(message)
    
    if success:
        print("✅ Signal message sent successfully!")
    else:
        print("❌ Failed to send signal message.")
    
    return success


def test_exit_message():
    """Test sending an exit signal message"""
    print("\nTesting exit signal message...")
    
    # Mock exit signal
    test_exit = {
        "signal": "EXIT",
        "exit_price": 1269.90,
        "reason": "TP HIT"
    }
    
    message = format_signal_message("INE467B01029", test_exit)
    success = send_telegram_alert(message)
    
    if success:
        print("✅ Exit message sent successfully!")
    else:
        print("❌ Failed to send exit message.")
    
    return success


def main():
    print("=" * 50)
    print("Stock Advanced Bot - Telegram Test")
    print("=" * 50)
    print()
    
    # Check configuration
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_ids = os.getenv("TELEGRAM_CHAT_IDS")
    
    if not bot_token or bot_token == "your_bot_token_here":
        print("❌ ERROR: TELEGRAM_BOT_TOKEN not configured in .env file")
        print("Please set your bot token from @BotFather")
        return
    
    if not chat_ids or chat_ids == "your_chat_id_here":
        print("❌ ERROR: TELEGRAM_CHAT_IDS not configured in .env file")
        print("Please set your chat ID (get it from bot messages)")
        return
    
    print(f"Bot Token: {bot_token[:20]}...")
    print(f"Chat IDs: {chat_ids}")
    print()
    
    # Run tests
    test1 = test_basic_message()
    
    if test1:
        input("\nPress Enter to send test BUY signal...")
        test2 = test_signal_message()
        
        input("\nPress Enter to send test EXIT signal...")
        test3 = test_exit_message()
        
        if test1 and test2 and test3:
            print("\n" + "=" * 50)
            print("✅ All tests passed!")
            print("Your Telegram integration is working correctly.")
            print("=" * 50)
        else:
            print("\n⚠️ Some tests failed. Check the output above.")
    else:
        print("\n❌ Initial test failed. Cannot proceed with other tests.")
        print("Fix the configuration and try again.")


if __name__ == "__main__":
    main()
