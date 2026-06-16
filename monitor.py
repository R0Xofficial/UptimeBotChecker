import asyncio
import logging
import os
import time
from datetime import datetime
import aiohttp
from dotenv import load_dotenv
from pyrogram import Client, filters

# --- LOGGING CONFIGURATION ---
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

# Silence library chatter
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logger = logging.getLogger("UptimeMonitor")

class UptimeMonitor:
    def __init__(self):
        load_dotenv()
        
        # Load and Validate Configuration
        self.api_id = os.getenv("API_ID")
        self.api_hash = os.getenv("API_HASH")
        self.session_string = os.getenv("SESSION_STRING")
        self.target = os.getenv("TARGET_BOT")
        self.interval = int(os.getenv("CHECK_INTERVAL", 60))
        self.timeout = int(os.getenv("TIMEOUT", 15))
        
        self.alert_token = os.getenv("ALERT_BOT_TOKEN")
        self.alert_chat_id = os.getenv("ALERT_CHAT_ID")

        if not all([self.api_id, self.api_hash, self.session_string, self.alert_token]):
            logger.critical("Missing core variables in .env! Check API_ID, API_HASH, SESSION_STRING, and ALERT_BOT_TOKEN.")
            exit(1)

        # Initialize Userbot with Session String
        self.userbot = Client(
            name="uptime_session",
            api_id=self.api_id,
            api_hash=self.api_hash,
            session_string=self.session_string,
            in_memory=True # We don't need a .session file when using a string
        )
        
        self.is_down = False
        self.down_start_time = None
        self.last_response_time = time.time()

    async def send_telegram_alert(self, message: str):
        """Sends an alert via the external Bot API using aiohttp."""
        url = f"https://api.telegram.org/bot{self.alert_token}/sendMessage"
        payload = {
            "chat_id": self.alert_chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        logger.info("Alert dispatched successfully.")
                    else:
                        error_details = await resp.text()
                        logger.error(f"Telegram API rejected alert: {error_details}")
            except Exception as e:
                logger.error(f"Networking error while sending alert: {e}")

    @staticmethod
    def format_duration(seconds: float) -> str:
        """Helper to format downtime duration."""
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0: return f"{h}h {m}m {s}s"
        if m > 0: return f"{m}m {s}s"
        return f"{s}s"

    async def run(self):
        """Main entry point for the monitor."""
        logger.info(f"Monitor service starting for target: @{self.target}")
        
        # Define Handler for Responses
        @self.userbot.on_message(filters.chat(self.target))
        async def incoming_handler(client, message):
            # Update last response timestamp
            if self.is_down:
                duration = self.format_duration(time.time() - self.down_start_time)
                now_str = datetime.now().strftime("%H:%M:%S (GMT+03:00)")
                
                recovery_text = (
                    "🟢 **Uptime Recovery**\n\n"
                    f"@{self.target} is back up!\n"
                    f"**Downtime:** {duration}\n"
                    f"**Recovered at:** {now_str}"
                )
                await self.send_telegram_alert(recovery_text)
                logger.info(f"RECOVERY: @{self.target} is back online after {duration}.")
                self.is_down = False
            
            self.last_response_time = time.time()
            logger.debug(f"Received heartbeat from @{self.target}")

        async with self.userbot:
            logger.info("Userbot connection established.")
            # Start the background checking loop
            asyncio.create_task(self.monitor_loop())
            # Keep the script running
            await asyncio.idle()

    async def monitor_loop(self):
        """Background task that probes the target bot."""
        while True:
            probe_time = time.time()
            logger.info(f"Probing @{self.target}...")
            
            try:
                # Sending /start as a ping
                await self.userbot.send_message(self.target, "/start")
            except Exception as e:
                logger.error(f"Userbot failed to send probe: {e}")

            # Wait for the response within the timeout window
            await asyncio.sleep(self.timeout)

            # Check if target bot replied after we sent the probe
            if self.last_response_time < probe_time:
                if not self.is_down:
                    self.is_down = True
                    self.down_start_time = time.time()
                    logger.warning(f"ALERT: @{self.target} is unresponsive!")
                    
                    alert_text = f"🚨 **Uptime Alert**\n\n@{self.target} is not responding!"
                    await self.send_telegram_alert(alert_text)
            
            # Calculate sleep to maintain a steady interval
            sleep_time = self.interval - self.timeout
            await asyncio.sleep(max(sleep_time, 1))

if __name__ == "__main__":
    monitor = UptimeMonitor()
    try:
        asyncio.run(monitor.run())
    except KeyboardInterrupt:
        logger.info("System exit requested. Monitor stopped.")
