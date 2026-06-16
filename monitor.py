import asyncio
import logging
import os
import time
from datetime import datetime
import aiohttp
from dotenv import load_dotenv
from pyrogram import Client, filters, idle

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
        self.timeout = int(os.getenv("TIMEOUT", 15)) # How long to wait for answer
        self.alert_token = os.getenv("ALERT_BOT_TOKEN")
        self.alert_chat_id = os.getenv("ALERT_CHAT_ID")

        self.userbot = Client(
            "monitor_session", 
            api_id=self.api_id, 
            api_hash=self.api_hash, 
            session_string=self.session_string,
            in_memory=True
        )
        
        self.is_down = False
        self.down_start_time = None
        self.last_response_time = 0
        self.last_probe_time = 0

    async def update_bot_bio(self, state: str):
        """Updates the Alerter Bot's Bio."""
        url = f"https://api.telegram.org/bot{self.alert_token}/setMyDescription"
        status_text = "Status: 🟢 Online" if state == "ONLINE" else "Status: 🚨 Offline"
        full_bio = f"{status_text} | Monitoring @{self.target}\nLast check: {datetime.now().strftime('%H:%M:%S')}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json={"description": full_bio}) as resp:
                    if resp.status != 200:
                        logger.error(f"Bio update failed: {await resp.text()}")
            except Exception as e:
                logger.error(f"Error updating bio: {e}")

    async def send_alert(self, message: str):
        """Sends markdown alert to the channel."""
        url = f"https://api.telegram.org/bot{self.alert_token}/sendMessage"
        payload = {"chat_id": self.alert_chat_id, "text": message, "parse_mode": "Markdown"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        logger.error(f"Alert failed: {await resp.text()}")
            except Exception as e:
                logger.error(f"Alert connection error: {e}")

    def format_downtime(self, seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0: return f"{h}h {m}m {s}s"
        if m > 0: return f"{m}m {s}s"
        return f"{s}s"

    async def check_loop(self):
        """Active probe loop: Send -> Wait Timeout -> Check."""
        await self.update_bot_bio("ONLINE")

        while True:
            # 1. Record probe time and send message
            self.last_probe_time = time.time()
            logger.info(f"Sending probe to @{self.target}...")
            
            try:
                await self.userbot.send_message(self.target, "/start")
            except Exception as e:
                logger.error(f"Failed to send probe: {e}")

            # 2. WAIT EXACTLY THE TIMEOUT PERIOD
            await asyncio.sleep(self.timeout)

            # 3. VERIFY IF BOT RESPONDED SINCE PROBE WAS SENT
            if self.last_response_time < self.last_probe_time:
                # Bot failed to respond within the timeout window
                if not self.is_down:
                    self.is_down = True
                    self.down_start_time = time.time()
                    
                    logger.warning(f"NO RESPONSE from @{self.target} after {self.timeout}s!")
                    
                    await self.send_alert(f"🚨 **Uptime Alert**\n\n@{self.target} is not responding!")
                    await self.update_bot_bio("OFFLINE")
            else:
                # Bot responded, ensure status is online
                if not self.is_down:
                    await self.update_bot_bio("ONLINE")
            
            # 4. SLEEP FOR THE REST OF THE INTERVAL
            # (Interval minus the time we already spent waiting for the timeout)
            remaining_sleep = self.interval - self.timeout
            await asyncio.sleep(max(remaining_sleep, 1))

    async def start(self):
        @self.userbot.on_message(filters.chat(self.target))
        async def on_reply(client, message):
            self.last_response_time = time.time()
            
            if self.is_down:
                # Recovery logic
                duration = self.format_downtime(self.last_response_time - self.down_start_time)
                now_str = datetime.now().strftime("%H:%M:%S")
                
                logger.info(f"Recovery detected for @{self.target}!")
                
                await self.send_alert(
                    f"🟢 **Uptime Recovery**\n\n@{self.target} is back up!\n"
                    f"**Downtime:** {duration}\n**Recovered at:** {now_str}"
                )
                await self.update_bot_bio("ONLINE")
                self.is_down = False

        logger.info("Connecting Userbot...")
        await self.userbot.start()
        
        asyncio.create_task(self.check_loop())
        logger.info("System fully operational.")
        await idle()
        await self.userbot.stop()

if __name__ == "__main__":
    monitor = UptimeMonitor()
    try:
        asyncio.run(monitor.start())
    except KeyboardInterrupt:
        logger.info("Exiting...")
