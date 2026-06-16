import asyncio
import logging
import os
import time
from datetime import datetime
import aiohttp
from dotenv import load_dotenv
from pyrogram import Client, filters, idle

# --- LOGGER ---
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
        
        # PRZECHOWUJEMY ID WYSŁANEJ WIADOMOŚCI
        self.last_probe_id = None

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
            logger.info(f"Probing @{self.target}...")
            
            try:
                # WYSYŁAMY WIADOMOŚĆ I ZAPISUJEMY JEJ OBIEKT
                sent_msg = await self.userbot.send_message(self.target, "/start")
                self.last_probe_id = sent_msg.id # TO JEST NASZE ID REFERENCYJNE
                
            except Exception as e:
                logger.error(f"Failed to send probe: {e}")

            try:
                # Czekamy na sygnał z handlera
                await asyncio.wait_for(self.response_event.wait(), timeout=self.timeout)
                logger.info(f"Verified specific response from @{self.target}.")
                
            except asyncio.TimeoutError:
                if not self.is_down:
                    self.is_down = True
                    self.down_start_time = time.time()
                    logger.warning(f"TIMEOUT: @{self.target} didn't reply to msg {self.last_probe_id}")
                    await self.send_alert(f"🚨 **Uptime Alert**\n\n@{self.target} is not responding!")
                    await self.update_bot_bio("OFFLINE")
            
            await asyncio.sleep(self.interval)

    async def start(self):
        @self.userbot.on_message(filters.chat(self.target))
        async def on_reply(client, message):
            # LOGIKA PRZECHWYTYWANIA ODPOWIEDZI:
            
            # 1. Sprawdzamy czy to jest techniczny "Reply" na naszą wiadomość
            is_technical_reply = (
                message.reply_to_message and 
                message.reply_to_message.id == self.last_probe_id
            )
            
            # 2. Fallback: Jeśli bot nie używa funkcji reply, sprawdzamy czy to po prostu 
            # nowa wiadomość od niego, która przyszła po wysłaniu sondy
            is_new_response = message.id > self.last_probe_id if self.last_probe_id else False

            if is_technical_reply or is_new_response:
                self.response_event.set()
                
                if self.is_down:
                    duration = int(time.time() - self.down_start_time)
                    await self.send_alert(
                        f"🟢 **Uptime Recovery**\n\n@{self.target} is back up!\n"
                        f"**Downtime:** {duration}s\n**Recovered at:** {datetime.now().strftime('%H:%M:%S')}"
                    )
                    await self.update_bot_bio("ONLINE")
                    self.is_down = False

        logger.info("Connecting Userbot...")
        await self.userbot.start()
        asyncio.create_task(self.check_loop())
        await idle()
        await self.userbot.stop()

if __name__ == "__main__":
    monitor = UptimeMonitor()
    try: asyncio.run(monitor.start())
    except KeyboardInterrupt: logger.info("Stopped.")
