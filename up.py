import asyncio
import logging
import os
import time
from datetime import datetime, timezone
import aiohttp
from dotenv import load_dotenv
from pyrogram import Client, idle
from pyrogram.errors import FloodWait

# --- SYSTEM LOGGING ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logging.getLogger("pyrogram").setLevel(logging.WARNING)

class UptimeMonitor:
    def __init__(self):
        load_dotenv()
        self.api_id = os.getenv("API_ID")
        self.api_hash = os.getenv("API_HASH")
        self.session_string = os.getenv("SESSION_STRING")
        self.target = os.getenv("TARGET_BOT").replace("@", "")
        self.interval = int(os.getenv("CHECK_INTERVAL", 10))
        self.timeout = int(os.getenv("TIMEOUT", 5))
        self.alert_token = os.getenv("ALERT_BOT_TOKEN")
        self.alert_chat_id = os.getenv("ALERT_CHAT_ID")

        self.userbot = None 
        self.is_down = False
        self.down_start_time = None

    async def send_alert(self, status: str, downtime: str = None, error_msg: str = None):
        url = f"https://api.telegram.org/bot{self.alert_token}/sendMessage"
        utc_now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        if status == "DOWN":
            text = (
                "🚨 **Uptime Alert!**\n\n"
                f"@{self.target} not responding!\n"
                f"**Timestamp:** `{utc_now}`"
            )
        elif status == "UP":
            text = (
                "🟢 **Return Alert!**\n\n"
                f"@{self.target} is back!\n"
                f"**Downtime:** `{downtime}`\n"
                f"**Timestamp:** `{utc_now}`"
            )
        elif status == "ERROR":
            text = (
                "⚠️ **Monitor Error!**\n\n"
                f"**Issue:** `{error_msg}`\n"
                f"**Timestamp:** `{utc_now}`"
            )

        payload = {"chat_id": self.alert_chat_id, "text": text, "parse_mode": "Markdown"}
        async with aiohttp.ClientSession() as session:
            try:
                await session.post(url, json=payload, timeout=10)
            except:
                pass

    def format_downtime(self, seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0: return f"{h}h {m}m {s}s"
        if m > 0: return f"{m}m {s}s"
        return f"{s}s"

    async def check_loop(self):
        while True:
            probe_time = time.time()
            try:
                await self.userbot.send_message(self.target, "/uptime")
                await asyncio.sleep(self.timeout)
                
                history = []
                async for msg in self.userbot.get_chat_history(self.target, limit=3):
                    history.append(msg)
                
                responded = False
                for m in history:
                    if m.from_user and m.from_user.is_bot:
                        if m.date.timestamp() >= (probe_time - 2):
                            responded = True
                            break
                
                if responded:
                    if self.is_down:
                        dt_str = self.format_downtime(time.time() - self.down_start_time)
                        await self.send_alert("UP", downtime=dt_str)
                        self.is_down = False
                else:
                    if not self.is_down:
                        self.is_down = True
                        self.down_start_time = time.time()
                        await self.send_alert("DOWN")

            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception as e:
                if int(time.time()) % 300 < self.interval:
                    await self.send_alert("ERROR", error_msg=str(e)[:100])

            await asyncio.sleep(max(self.interval - self.timeout, 1))

    async def start(self):
        self.userbot = Client(
            "uptime_session",
            api_id=self.api_id,
            api_hash=self.api_hash,
            session_string=self.session_string,
            in_memory=True
        )
        
        await self.userbot.start()
        print(f"Monitor active: @{self.target}")
        asyncio.create_task(self.check_loop())
        await idle()
        await self.userbot.stop()

if __name__ == "__main__":
    monitor = UptimeMonitor()
    try:
        asyncio.run(monitor.start())
    except KeyboardInterrupt:
        pass
