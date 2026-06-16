import asyncio
import logging
import os
import time
from datetime import datetime
import aiohttp
from dotenv import load_dotenv
from pyrogram import Client, filters, idle  # Importujemy idle stąd

# --- LOGGER CONFIGURATION ---
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logger = logging.getLogger("UptimeMonitor")

class UptimeMonitor:
    def __init__(self):
        load_dotenv()
        self.api_id = os.getenv("API_ID")
        self.api_hash = os.getenv("API_HASH")
        self.session_string = os.getenv("SESSION_STRING")
        self.target = os.getenv("TARGET_BOT")
        self.interval = int(os.getenv("CHECK_INTERVAL", 60))
        self.timeout = int(os.getenv("TIMEOUT", 15))
        self.alert_token = os.getenv("ALERT_BOT_TOKEN")
        self.alert_chat_id = os.getenv("ALERT_CHAT_ID")

        if not all([self.api_id, self.api_hash, self.session_string, self.alert_token]):
            logger.error("Missing configuration in .env file!")
            exit(1)

        # Ustawiamy in_memory=True, żeby nie tworzył plików bazy danych
        self.userbot = Client(
            "monitor_session", 
            api_id=self.api_id, 
            api_hash=self.api_hash, 
            session_string=self.session_string,
            in_memory=True
        )
        
        self.is_down = False
        self.down_start_time = None
        self.last_response_time = time.time()

    async def send_alert(self, message: str):
        url = f"https://api.telegram.org/bot{self.alert_token}/sendMessage"
        payload = {"chat_id": self.alert_chat_id, "text": message, "parse_mode": "Markdown"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        logger.error(f"Alert Error: {await resp.text()}")
            except Exception as e:
                logger.error(f"Alerter connection error: {e}")

    def format_downtime(self, seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h}h {m}m {s}s" if h > 0 else f"{m}m {s}s" if m > 0 else f"{s}s"

    async def check_loop(self):
        """Background task that periodically pings the target bot."""
        while True:
            sent_time = time.time()
            logger.info(f"Probing @{self.target}...")
            try:
                await self.userbot.send_message(self.target, "/uptime")
            except Exception as e:
                logger.error(f"Failed to send ping: {e}")
            
            await asyncio.sleep(self.timeout)

            if self.last_response_time < sent_time:
                if not self.is_down:
                    self.is_down = True
                    self.down_start_time = time.time()
                    alert_msg = f"🚨 **Uptime Alert**\n\n@{self.target} is not responding!"
                    await self.send_alert(alert_msg)
                    logger.warning("Target is DOWN!")
            
            await asyncio.sleep(max(self.interval - self.timeout, 1))

    async def start(self):
        # Definiujemy handlera wewnątrz start()
        @self.userbot.on_message(filters.chat(self.target))
        async def handle_reply(client, message):
            if self.is_down:
                duration = self.format_downtime(time.time() - self.down_start_time)
                now_str = datetime.now().strftime("%H:%M:%S")
                msg = (
                    f"🟢 **Uptime Recovery**\n\n@{self.target} is back up!\n"
                    f"**Downtime:** {duration}\n**Recovered at:** {now_str}"
                )
                await self.send_alert(msg)
                self.is_down = False
            self.last_response_time = time.time()

        logger.info("Starting Userbot...")
        await self.userbot.start()
        logger.info("Userbot started. Launching monitor loop...")
        
        # Uruchamiamy pętlę sprawdzającą w tle
        asyncio.create_task(self.check_loop())
        
        # Używamy idle() z pyrograma, aby skrypt działał
        await idle()
        
        # Na koniec bezpiecznie zatrzymujemy
        await self.userbot.stop()

if __name__ == "__main__":
    monitor = UptimeMonitor()
    try:
        asyncio.run(monitor.start())
    except KeyboardInterrupt:
        logger.info("Monitor stopped.")
