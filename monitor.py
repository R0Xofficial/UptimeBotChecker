import asyncio
import logging
import os
import time
from datetime import datetime
import aiohttp
from dotenv import load_dotenv
from pyrogram import Client, filters, idle

# --- PROFESSIONAL LOGGING ---
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
        self.target = os.getenv("TARGET_BOT").replace("@", "")
        self.interval = int(os.getenv("CHECK_INTERVAL", 60))
        self.timeout = int(os.getenv("TIMEOUT", 15))
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
        self.response_event = asyncio.Event()
        self.last_probe_id = 0

    async def update_bot_bio(self, state: str):
        url = f"https://api.telegram.org/bot{self.alert_token}/setMyDescription"
        emoji = "🟢 Online" if state == "ONLINE" else "🚨 Offline"
        full_bio = f"Status: {emoji} | Monitoring @{self.target}\nLast update: {datetime.now().strftime('%H:%M:%S')}"
        async with aiohttp.ClientSession() as session:
            try: await session.post(url, json={"description": full_bio})
            except: pass

    async def send_alert(self, message: str):
        url = f"https://api.telegram.org/bot{self.alert_token}/sendMessage"
        payload = {"chat_id": self.alert_chat_id, "text": message, "parse_mode": "Markdown"}
        async with aiohttp.ClientSession() as session:
            try: await session.post(url, json=payload)
            except: pass

    async def check_loop(self):
        await self.update_bot_bio("ONLINE")
        while True:
            self.response_event.clear()
            logger.info(f"Sending probe to @{self.target}...")
            
            try:
                # Wysyłamy wiadomość i zapisujemy jej ID
                sent_msg = await self.userbot.send_message(self.target, "/start")
                self.last_probe_id = sent_msg.id
                
                # Czekamy na sygnał (Event) z handlera
                try:
                    await asyncio.wait_for(self.response_event.wait(), timeout=self.timeout)
                    logger.info(f"Successfully verified response from @{self.target}.")
                except asyncio.TimeoutError:
                    if not self.is_down:
                        self.is_down = True
                        self.down_start_time = time.time()
                        logger.warning(f"ALERT: No response from @{self.target} within {self.timeout}s.")
                        await self.send_alert(f"🚨 **Uptime Alert**\n\n@{self.target} is not responding!")
                        await self.update_bot_bio("OFFLINE")
            
            except Exception as e:
                logger.error(f"Error sending probe: {e}")

            await asyncio.sleep(self.interval)

    async def start(self):
        # USUNĘLIŚMY filters.reply - teraz łapiemy KAŻDĄ wiadomość od bota
        @self.userbot.on_message(filters.chat(self.target))
        async def on_any_message(client, message):
            # Logika sprawdzająca: czy ta wiadomość jest nowsza niż nasza sonda?
            if message.id > self.last_probe_id:
                logger.info(f"Received new message (ID: {message.id}) from @{self.target}. Pulse confirmed.")
                
                # Zapalamy flage (Event), co budzi pętle check_loop
                self.response_event.set()
                
                if self.is_down:
                    downtime = int(time.time() - self.down_start_time)
                    now_str = datetime.now().strftime("%H:%M:%S")
                    await self.send_alert(
                        f"🟢 **Uptime Recovery**\n\n@{self.target} is back up!\n"
                        f"**Downtime:** {downtime}s\n**Recovered at:** {now_str}"
                    )
                    await self.update_bot_bio("ONLINE")
                    self.is_down = False
            else:
                logger.debug("Received an old message or our own probe. Ignoring.")

        logger.info("Connecting Userbot...")
        await self.userbot.start()
        
        asyncio.create_task(self.check_loop())
        logger.info("Monitor active. Waiting for pulses...")
        await idle()
        await self.userbot.stop()

if __name__ == "__main__":
    monitor = UptimeMonitor()
    try: asyncio.run(monitor.start())
    except KeyboardInterrupt: logger.info("Stopped.")
