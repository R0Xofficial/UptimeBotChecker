import asyncio
import logging
import os
import time
from datetime import datetime
import aiohttp
from dotenv import load_dotenv
from pyrogram import Client, filters

# Load environment variables
load_dotenv()

# --- LOGGER CONFIGURATION ---
# We use a custom format and prevent libraries from flooding the console
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logger = logging.getLogger("UptimeMonitor")

class UptimeMonitor:
    def __init__(self):
        # Load config from .env
        self.api_id = os.getenv("API_ID")
        self.api_hash = os.getenv("API_HASH")
        self.target = os.getenv("TARGET_BOT")
        self.interval = int(os.getenv("CHECK_INTERVAL", 60))
        self.timeout = int(os.getenv("TIMEOUT", 15))
        
        self.alert_token = os.getenv("ALERT_BOT_TOKEN")
        self.alert_chat_id = os.getenv("ALERT_CHAT_ID")

        # Validation
        if not all([self.api_id, self.api_hash, self.target, self.alert_token]):
            logger.error("Missing configuration in .env file!")
            exit(1)

        self.userbot = Client("monitor_session", api_id=self.api_id, api_hash=self.api_hash)
        
        self.is_down = False
        self.down_start_time = None
        self.last_response_time = time.time()

    async def send_alert(self, message: str):
        """Dispatches an alert via the external Telegram Bot API."""
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
                        logger.info("Alert successfully delivered to Telegram.")
                    else:
                        logger.error(f"Telegram API Error: {await resp.text()}")
            except Exception as e:
                logger.error(f"Failed to connect to Telegram Bot API: {e}")

    @staticmethod
    def format_downtime(seconds: float) -> str:
        """Converts seconds into a human-readable format."""
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h}h {m}m {s}s" if h > 0 else f"{m}m {s}s" if m > 0 else f"{s}s"

    async def start(self):
        logger.info(f"Initializing monitor for @{self.target}...")
        
        # Register the handler for the target bot's messages
        @self.userbot.on_message(filters.chat(self.target))
        async def handle_reply(client, message):
            if self.is_down:
                duration = self.format_downtime(time.time() - self.down_start_time)
                now_str = datetime.now().strftime("%H:%M:%S (GMT+03:00)")
                
                msg = (
                    "🟢 **Uptime Recovery**\n\n"
                    f"@{self.target} is back up!\n"
                    f"**Downtime:** {duration}\n"
                    f"**Recovered at:** {now_str}"
                )
                await self.send_alert(msg)
                logger.info(f"Target @{self.target} recovered. Downtime was {duration}.")
                self.is_down = False
            
            self.last_response_time = time.time()

        async with self.userbot:
            logger.info("Userbot session active. Starting health checks...")
            asyncio.create_task(self.check_loop())
            await asyncio.idle()

    async def check_loop(self):
        """Background task that periodically pings the target bot."""
        while True:
            sent_time = time.time()
            logger.debug(f"Sending probe to @{self.target}...")
            
            try:
                await self.userbot.send_message(self.target, "/start")
            except Exception as e:
                logger.error(f"RPC Error: Could not send message to @{self.target}: {e}")
            
            # Wait for the response within the timeout window
            await asyncio.sleep(self.timeout)

            if self.last_response_time < sent_time:
                if not self.is_down:
                    self.is_down = True
                    self.down_start_time = time.time()
                    logger.warning(f"Detection: @{self.target} is UNRESPONSIVE.")
                    
                    alert_msg = f"🚨 **Uptime Alert**\n\n@{self.target} is not responding!"
                    await self.send_alert(alert_msg)
            
            # Sleep until the next check cycle
            await asyncio.sleep(self.interval - self.timeout)

if __name__ == "__main__":
    monitor = UptimeMonitor()
    try:
        asyncio.run(monitor.start())
    except KeyboardInterrupt:
        logger.info("Monitor shutting down...")
