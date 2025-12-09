"""
Launcher script to run both main.py and telegram_bot.py concurrently
"""
import os
import sys
import threading
import time
from datetime import datetime


def run_main():
    """Run the main trading bot"""
    print(f"[{datetime.now()}] Starting main trading bot...")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'core_logic'))
    
    try:
        # Import and run main
        import main
        main.main()
    except Exception as e:
        print(f"[{datetime.now()}] Error in main.py: {e}")
        import traceback
        traceback.print_exc()


def run_telegram_bot():
    """Run the Telegram bot"""
    print(f"[{datetime.now()}] Starting Telegram bot...")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'telegram_bot'))
    
    try:
        # Import and run telegram bot
        from telegram_bot import telegram_bot
        telegram_bot.run_telegram_bot()
    except Exception as e:
        print(f"[{datetime.now()}] Error in telegram_bot.py: {e}")
        import traceback
        traceback.print_exc()


def main():
    print("="*60)
    print("Starting Stock Advanced Bot - Dual Mode")
    print("="*60)
    print(f"Time: {datetime.now()}")
    print()
    
    # Create threads for both processes
    main_thread = threading.Thread(target=run_main, name="MainBot", daemon=False)
    telegram_thread = threading.Thread(target=run_telegram_bot, name="TelegramBot", daemon=False)
    
    # Start both threads
    print("Launching both services...")
    main_thread.start()
    time.sleep(2)  # Give main a head start
    telegram_thread.start()
    
    print()
    print("Both services are running!")
    print("Press CTRL+C to stop both services")
    print("="*60)
    print()
    
    try:
        # Keep the main thread alive
        while True:
            if not main_thread.is_alive():
                print(f"\n[{datetime.now()}] WARNING: Main bot thread stopped!")
            if not telegram_thread.is_alive():
                print(f"\n[{datetime.now()}] WARNING: Telegram bot thread stopped!")
            
            time.sleep(5)
    except KeyboardInterrupt:
        print(f"\n[{datetime.now()}] Stopping both services...")
        print("Waiting for threads to finish...")
        main_thread.join(timeout=5)
        telegram_thread.join(timeout=5)
        print("All services stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
