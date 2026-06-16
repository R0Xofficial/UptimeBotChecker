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
        self.timeout = int(os.getenv("TIMEOUT", 15))
        self.alert_token = os.getenv("ALERT_BOT_TOKEN")
        self.alert_chat_id = os.getenv("ALERT_CHAT_ID")

        # Session in RAM to avoid file issues in Termux
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

    async def update_bot_bio(self, state: str):
        """Updates the Alerter Bot's Bio based on state."""
        # Using setMyDescription for the main bot profile bio
        url = f"https://api.telegram.org/bot{self.alert_token}/setMyDescription"
        
        if state == "ONLINE":
            status_text = f"Status: 🟢 Online | Monitoring @{self.target}"
        else:
            status_text = f"Status: 🚨 Offline | Monitoring @{self.target}"
        
        # Add timestamp to know the bot is still running
        full_bio = f"{status_text}\nLast check: {datetime.now().strftime('%H:%M:%S')}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json={"description": full_bio}) as resp:
                    if resp.status == 200:
                        logger.info(f"Bio updated to {state}")
                    else:
                        logger.error(f"Bio update failed: {await resp.text()}")
            except Exception as e:
                logger.error(f"Error connecting to Bot API for bio: {e}")

    async def send_alert(self, message: str):
        """Dispatches alert to the channel."""
        url = f"https://api.telegram.org/bot{self.alert_token}/sendMessage"
        payload = {"chat_id": self.alert_chat_id, "text": message, "parse_mode": "Markdown"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        logger.error(f"SendMessage error: {await resp.text()}")
            except Exception as e:
                logger.error(f"Alerter connection error: {e}")

    def format_downtime(self, seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h}h {m}m {s}s" if h > 0 else f"{m}m {s}s" if m > 0 else f"{s}s"

    async def check_loop(self):
        """Background worker for heartbeats."""
        # Initial status
        await self.update_bot_bio("ONLINE")

        while True:
            probe_start = time.time()
            logger.info(f"Pinging @{self.target}...")
            try:
                await self.userbot.send_message(self.target, "/uptime")
            except Exception as e:
                logger.error(f"RPC Error sending ping: {e}")
            
            await asyncio.sleep(self.timeout)

            # Check if bot responded
            if self.last_response_time < probe_start:
                # If bot is not responding AND we haven't sent the alert yet
                if not self.is_down:
                    self.is_down = True
                    self.down_start_time = time.time()
                    
                    # 1. Send the Alert Message (ONLY ONCE)
                    alert_msg = f"🚨 **Uptime Alert**\n\n@{self.target} is not responding!"
                    await self.send_alert(alert_msg)
                    
                    # 2. Change Bio to Offline
                    await self.update_bot_bio("OFFLINE")
                    logger.warning(f"Detection: @{self.target} is DOWN. Bio updated.")
            
            await asyncio.sleep(max(self.interval - self.timeout, 1))

    async def start(self):
        @self.userbot.on_message(filters.chat(self.target))
        async def on_reply(client, message):
            if self.is_down:
                # Bot was down and just replied
                duration = self.format_downtime(time.time() - self.down_start_time)
                now_str = datetime.now().strftime("%H:%M:%S")
                
                # 1. Send Recovery Message
                recovery_msg = (
                    f"🟢 **Uptime Recovery**\n\n@{self.target} is back up!\n"
                    f"**Downtime:** {duration}\n**Recovered at:** {now_str}"
                )
                await self.send_alert(recovery_msg)
                
                # 2. Restore Bio to Online
                await self.update_bot_bio("ONLINE")
                self.is_down = False
                logger.info(f"Detection: @{self.target} is UP. Bio restored.")
            
            self.last_response_time = time.time()

        logger.info("Initializing Userbot Client...")
        await self.userbot.start()
        
        asyncio.create_task(self.check_loop())
        logger.info("Monitoring active.")
        await idle()
        await self.userbot.stop()

if __name__ == "__main__":
    monitor = UptimeMonitor()
    try:
        asyncio.run(monitor.start())
    except KeyboardInterrupt:
        logger.info("Service stopping...")
