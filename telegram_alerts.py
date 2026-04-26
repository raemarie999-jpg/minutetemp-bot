import os
import requests


class TelegramAlerts:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def send(self, message: str):
        if not self.token or not self.chat_id:
            print("⚠️ Telegram not configured")
            return

        try:
            requests.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": message
                },
                timeout=5
            )
        except Exception as e:
            print("Telegram error:", e)
