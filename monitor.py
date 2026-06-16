import asyncio
import logging
import os
import time
from datetime import datetime, timezone
import aiohttp
from dotenv import load_dotenv
from pyrogram import Client, idle

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

    async def send_alert(self, status: str, downtime: str = None):
        """Sends alerts with custom formatting and UTC timestamps."""
        url = f"https://api.telegram.org/bot{self.alert_token}/sendMessage"
        utc_now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        if status == "DOWN":
            text = (
                "🚨 **Uptime Alert!**\n\n"
                f"**Target:** @{self.target}\n"
                f"**Status:** `not responding!`\n"
                f"**Timestamp:** `{utc_now}`"
            )
        else:
            text = (
                "🟢 **Return Alert!**\n\n"
                f"**Target:** @{self.target}\n"
                f"**Status:** `is back!`\n"
                f"**Downtime:** `{downtime}`\n"
                f"**Timestamp:** `{utc_now}`"
            )

        payload = {
            "chat_id": self.alert_chat_id, 
            "text": text, 
            "parse_mode": "Markdown"
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload) as resp:
                    pass
            except:
                pass

    def format_downtime(self, seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0: return f"{h}h {m}m {s}s"
        if m > 0: return f"{m}m {s}s"
        return f"{s}s"

    async def check_loop(self):
        """History-based monitoring logic."""
        while True:
            probe_time = time.time()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Pinging @{self.target}...")
            
            try:
                # 1. Send probe
                await self.userbot.send_message(self.target, "/start")
                
                # 2. Wait for response
                await asyncio.sleep(self.timeout)
                
                # 3. Fetch history
                history = []
                async for msg in self.userbot.get_chat_history(self.target, limit=5):
                    history.append(msg)
                
                # 4. Analyze history (5s grace period for clock drift)
                responded = False
                for m in history:
                    if m.from_user and m.from_user.is_bot:
                        if m.date.timestamp() >= (probe_time - 5):
                            responded = True
                            break
                
                if responded:
                    if self.is_down:
                        dt_str = self.format_downtime(time.time() - self.down_start_time)
                        await self.send_alert("UP", downtime=dt_str)
                        self.is_down = False
                        print(f"Recovery: @{self.target}")
                else:
                    if not self.is_down:
                        self.is_down = True
                        self.down_start_time = time.time()
                        await self.send_alert("DOWN")
                        print(f"Alert: @{self.target} is Down")

            except Exception as e:
                print(f"Loop Error: {e}")

            # Wait for next check
            await asyncio.sleep(max(self.interval - self.timeout, 1))

    async def start(self):
        print("Connecting userbot...")
        await self.userbot.start()
        print(f"Monitoring of @{self.target} is now active.")
        asyncio.create_task(self.check_loop())
        await idle()
        await self.userbot.stop()

if __name__ == "__main__":
    monitor = UptimeMonitor()
    try:
        asyncio.run(monitor.start())
    except KeyboardInterrupt:
        pass
