import asyncio
import logging
import os
import time
from datetime import datetime, timezone
import aiohttp
from dotenv import load_dotenv
from pyrogram import Client, filters, idle

# --- SZCZEGÓŁOWE LOGOWANIE ---
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
        
        # Monitor Config
        watch_val = os.getenv("WATCH_CHAT")
        if watch_val and (watch_val.startswith("-") or watch_val.isdigit()):
            self.watch_chat = int(watch_val)
        else:
            self.watch_chat = watch_val
            
        # USER DEFINED DISPLAY NAME
        # Jeśli nie podasz DISPLAY_NAME, użyje WATCH_CHAT
        self.target_display = os.getenv("DISPLAY_NAME") or watch_val
            
        self.target_display = f"@{watch_val}" if not str(watch_val).startswith("-") else f"Group({watch_val})"
        self.keyword = os.getenv("PULSE_KEYWORD")
        self.threshold = int(os.getenv("PULSE_THRESHOLD", 90))
        
        # Alerter Config
        self.alert_token = os.getenv("ALERT_BOT_TOKEN")
        alert_chat_val = os.getenv("ALERT_CHAT_ID")
        self.alert_chat_id = int(alert_chat_val) if alert_chat_val.startswith("-") or alert_chat_val.isdigit() else alert_chat_val

        self.userbot = None
        self.is_down = False
        self.down_start_time = None
        self.last_pulse_received = time.time()

    async def send_alert(self, status: str, downtime: str = None, error_msg: str = None):
        """Sends alerts and logs the exact API response."""
        url = f"https://api.telegram.org/bot{self.alert_token}/sendMessage"
        utc_now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        if status == "DOWN":
            text = (
                "🚨 **Uptime Alert!**\n\n"
                f"{self.target_display} not responding!\n"
                f"**Timestamp:** `{utc_now}`"
            )
        elif status == "UP":
            text = (
                "🟢 **Return Alert!**\n\n"
                f"{self.target_display} is back!\n"
                f"**Downtime:** `{downtime}`\n"
                f"**Timestamp:** `{utc_now}`"
            )
        else:
            text = (
                "⚠️ **Monitor Error!**\n\n"
                f"**Issue:** `{error_msg}`\n"
                f"**Timestamp:** `{utc_now}`"
            )

        payload = {"chat_id": self.alert_chat_id, "text": text, "parse_mode": "Markdown"}
        
        logger.info(f"Attempting to send {status} alert to {self.alert_chat_id}...")
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload, timeout=10) as resp:
                    result = await resp.json()
                    if resp.status == 200:
                        logger.info("✅ Alert sent successfully!")
                    else:
                        logger.error(f"❌ Telegram API rejected alert: {result.get('description')}")
            except Exception as e:
                logger.error(f"❌ Failed to connect to Telegram API: {e}")

    def format_downtime(self, seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0: return f"{h}h {m}m {s}s"
        if m > 0: return f"{m}m {s}s"
        return f"{s}s"

    async def watchdog_loop(self):
        """Monitors time since last pulse and logs status."""
        logger.info("Watchdog loop started.")
        while True:
            elapsed = time.time() - self.last_pulse_received
            
            # Log co każde 30 sekund, żeby nie spamić, ale pokazać że działa
            if int(elapsed) % 30 == 0 and int(elapsed) != 0:
                logger.info(f"Checking... {int(elapsed)}s since last pulse (Threshold: {self.threshold}s)")

            if elapsed > self.threshold:
                if not self.is_down:
                    self.is_down = True
                    self.down_start_time = self.last_pulse_received
                    logger.warning(f"🚨 Pulse missing for {int(elapsed)}s! Triggering ALERT.")
                    await self.send_alert("DOWN")
            
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
                logger.info(f"❤️ Pulse captured from {self.target_display}! Content: '{message.text[:20]}...'")
                
                if self.is_down:
                    dt = self.format_downtime(time.time() - self.down_start_time)
                    logger.info(f"💚 Recovery detected! Downtime: {dt}. Triggering RECOVERY alert.")
                    await self.send_alert("UP", downtime=dt)
                    self.is_down = False
                
                self.last_pulse_received = time.time()

        try:
            logger.info(f"Connecting Userbot for {self.target_display}...")
            await self.userbot.start()
            logger.info(f"Monitor active. Keyword: '{self.keyword}' | Threshold: {self.threshold}s")
            
            # Start watchdog
            asyncio.create_task(self.watchdog_loop())
            
            await idle()
            await self.userbot.stop()
        except Exception as e:
            logger.error(f"Critical start error: {e}")
            await self.send_alert("ERROR", error_msg=str(e)[:100])

if __name__ == "__main__":
    monitor = PassiveMonitor()
    try:
        asyncio.run(monitor.start())
    except KeyboardInterrupt:
        logger.info("Monitor stopped manually.")
