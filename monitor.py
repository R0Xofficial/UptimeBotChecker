import asyncio
import logging
import os
import time
from datetime import datetime
import aiohttp
from dotenv import load_dotenv
from pyrogram import Client, idle

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logger = logging.getLogger("UptimeMonitor")

class UptimeMonitor:
    def __init__(self):
        load_dotenv()
        self.api_id = os.getenv("API_ID")
        self.api_hash = os.getenv("API_HASH")
        self.session_string = os.getenv("SESSION_STRING")
        self.target = os.getenv("TARGET_BOT").replace("@", "")
        self.interval = int(os.getenv("CHECK_INTERVAL", 60))
        self.timeout = int(os.getenv("TIMEOUT", 15))
        self.alert_token = os.getenv("ALERT_BOT_TOKEN")
        self.alert_chat_id = os.getenv("ALERT_CHAT_ID")

        self.userbot = Client(
            "uptime_session",
            api_id=self.api_id,
            api_hash=self.api_hash,
            session_string=self.session_string,
            in_memory=True
        )
        
        self.is_down = False
        self.down_start_time = None

    async def update_bio(self, state: str):
        """Changes Alerter Bot's Bio."""
        url = f"https://api.telegram.org/bot{self.alert_token}/setMyDescription"
        emoji = "🟢 Online" if state == "ONLINE" else "🚨 Offline"
        text = f"Status: {emoji} | Monitoring @{self.target}\nLast check: {datetime.now().strftime('%H:%M:%S')}"
        async with aiohttp.ClientSession() as session:
            try: await session.post(url, json={"description": text})
            except: pass

    async def send_alert(self, message: str):
        """Sends alert message to the channel."""
        url = f"https://api.telegram.org/bot{self.alert_token}/sendMessage"
        payload = {"chat_id": self.alert_chat_id, "text": message, "parse_mode": "Markdown"}
        async with aiohttp.ClientSession() as session:
            try: await session.post(url, json=payload)
            except: pass

    def format_downtime(self, seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h}h {m}m {s}s" if h > 0 else f"{m}m {s}s" if m > 0 else f"{s}s"

    async def check_bot_status(self):
        """Pings the bot and then manually checks the history for a response."""
        while True:
            probe_time = time.time()
            logger.info(f"Probing @{self.target}...")
            
            try:
                # 1. Send the probe
                await self.userbot.send_message(self.target, "/start")
                
                # 2. Wait for the bot to respond
                await asyncio.sleep(self.timeout)
                
                # 3. MANUALLY CHECK CHAT HISTORY
                # Fetch last 3 messages to be sure
                history = []
                async for msg in self.userbot.get_chat_history(self.target, limit=3):
                    history.append(msg)
                
                # 4. Analyze history
                bot_responded = False
                for m in history:
                    # Check if message is FROM the bot AND was sent AFTER our probe
                    # (buffer -2 seconds for time sync issues)
                    if m.from_user and m.from_user.is_bot:
                        if m.date.timestamp() >= (probe_time - 2):
                            bot_responded = True
                            break
                
                if bot_responded:
                    logger.info(f"Bot @{self.target} is ALIVE.")
                    if self.is_down:
                        # RECOVERY
                        downtime = self.format_downtime(time.time() - self.down_start_time)
                        await self.send_alert(
                            f"🟢 **Uptime Recovery**\n\n@{self.target} is back up!\n"
                            f"**Downtime:** {downtime}\n**Recovered at:** {datetime.now().strftime('%H:%M:%S')}"
                        )
                        await self.update_bio("ONLINE")
                        self.is_down = False
                else:
                    # NO RESPONSE FOUND IN HISTORY
                    if not self.is_down:
                        self.is_down = True
                        self.down_start_time = time.time()
                        logger.warning(f"ALERT: @{self.target} is not responding (checked history).")
                        await self.send_alert(f"🚨 **Uptime Alert**\n\n@{self.target} is not responding!")
                        await self.update_bio("OFFLINE")

            except Exception as e:
                logger.error(f"Error during check: {e}")

            # Wait for next interval
            await asyncio.sleep(max(self.interval - self.timeout, 1))

    async def start(self):
        logger.info("Connecting Userbot...")
        await self.userbot.start()
        await self.update_bio("ONLINE")
        
        # Start the manual checker loop
        asyncio.create_task(self.check_bot_status())
        
        logger.info("Monitor is running (History Check mode).")
        await idle()
        await self.userbot.stop()

if __name__ == "__main__":
    monitor = UptimeMonitor()
    try:
        asyncio.run(monitor.start())
    except KeyboardInterrupt:
        logger.info("Exiting...")
