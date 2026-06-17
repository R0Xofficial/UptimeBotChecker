import asyncio
import logging
import os
import time
from datetime import datetime, timezone
import aiohttp
from dotenv import load_dotenv
from pyrogram import Client, filters, idle

# --- LOGI KONSOLOWE (Czyste) ---
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logger = logging.getLogger("Monitor")

class PassiveMonitor:
    def __init__(self):
        load_dotenv()
        self.api_id = os.getenv("API_ID")
        self.api_hash = os.getenv("API_HASH")
        self.session_string = os.getenv("SESSION_STRING")
        
        # Konfiguracja czatu
        watch_val = os.getenv("WATCH_CHAT")
        if watch_val and (watch_val.startswith("-") or watch_val.isdigit()):
            self.watch_chat = int(watch_val)
        else:
            self.watch_chat = watch_val
            
        self.target_display = os.getenv("DISPLAY_NAME") or watch_val
        self.keyword = os.getenv("PULSE_KEYWORD")
        self.threshold = int(os.getenv("PULSE_THRESHOLD", 90))
        
        # Konfiguracja Alertera
        self.alert_token = os.getenv("ALERT_BOT_TOKEN")
        alert_chat_val = os.getenv("ALERT_CHAT_ID")
        try:
            self.alert_chat_id = int(alert_chat_val)
        except:
            self.alert_chat_id = alert_chat_val

        # Stan logiczny
        self.userbot = None
        self.is_down = False
        self.down_start_time = None
        self.last_pulse_received = time.time()
        
        # Blokada przeciwko dublowaniu wiadomości
        self.status_lock = asyncio.Lock()

    async def send_alert(self, status: str, downtime: str = None, error_msg: str = None):
        """Wysyła wiadomości 1:1 zgodnie ze wzorem (Formatowanie HTML)."""
        url = f"https://api.telegram.org/bot{self.alert_token}/sendMessage"
        utc_now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        if status == "DOWN":
            text = (
                f"🚨 <b>Uptime Alert!</b>\n\n"
                f"{self.target_display} not responding!\n"
                f"<b>Timestamp:</b> <code>{utc_now}</code>"
            )
        elif status == "UP":
            text = (
                f"🟢 <b>Return Alert!</b>\n\n"
                f"{self.target_display} is back!\n"
                f"<b>Downtime:</b> <code>{downtime}</code>\n"
                f"<b>Timestamp:</b> <code>{utc_now}</code>"
            )
        else:
            text = (
                f"⚠️ <b>Monitor Error!</b>\n\n"
                f"<b>Issue:</b> <code>{error_msg}</code>\n"
                f"<b>Timestamp:</b> <code>{utc_now}</code>"
            )

        payload = {
            "chat_id": self.alert_chat_id, 
            "text": text, 
            "parse_mode": "HTML"
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload, timeout=10) as resp:
                    if resp.status == 200:
                        logger.info(f"Alert {status} sent.")
                    else:
                        logger.error(f"API Error: {await resp.text()}")
            except Exception as e:
                logger.error(f"Failed to send alert: {e}")

    def format_downtime(self, seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0: return f"{h}h {m}m {s}s"
        if m > 0: return f"{m}m {s}s"
        return f"{s}s"

    async def watchdog_loop(self):
        """Pętla sprawdzająca brak pulsu."""
        while True:
            elapsed = time.time() - self.last_pulse_received
            
            if elapsed > self.threshold:
                async with self.status_lock:
                    if not self.is_down:
                        self.is_down = True
                        self.down_start_time = self.last_pulse_received
                        logger.warning(f"Pulse missing for {int(elapsed)}s!")
                        await self.send_alert("DOWN")
            
            # Log statusu w konsoli co 30s
            if int(time.time()) % 30 < 1:
                logger.info(f"Status OK | Last pulse: {int(elapsed)}s ago")
                await asyncio.sleep(1)

            await asyncio.sleep(1)

    async def start(self):
        self.userbot = Client(
            "passive_monitor",
            api_id=self.api_id,
            api_hash=self.api_hash,
            session_string=self.session_string,
            in_memory=True
        )

        @self.userbot.on_message(filters.chat(self.watch_chat) & filters.text)
        async def on_pulse(client, message):
            if self.keyword in message.text:
                async with self.status_lock:
                    if self.is_down:
                        dt = self.format_downtime(time.time() - self.down_start_time)
                        logger.info("Recovery detected!")
                        await self.send_alert("UP", downtime=dt)
                        self.is_down = False
                    
                    self.last_pulse_received = time.time()
                    logger.info(f"Heartbeat from {self.target_display} captured.")

        try:
            await self.userbot.start()
            logger.info(f"Monitor active for {self.target_display}")
            asyncio.create_task(self.watchdog_loop())
            await idle()
            await self.userbot.stop()
        except Exception as e:
            logger.error(f"Error: {e}")

if __name__ == "__main__":
    monitor = PassiveMonitor()
    try:
        asyncio.run(monitor.start())
    except KeyboardInterrupt:
        logger.info("Stopped.")
