"""Telegram webhook for one client.

Usage:
    Use this class directly or inherit it for a client-specific Telegram hook.

Input spec:
    - Same inputs as `ClientWebhook`.

Output spec:
    - Returns a configured Telegram webhook instance.
"""
import sys
import json
import urllib.request

from webhooks.client_webhook import ClientWebhook

class TelegramWebhook(ClientWebhook):
    channel_name = "telegram"

    def __init__(
        self,
        client_name: str,
        client_json_path: str,
        webhook_url: str,
        webhook_secret: str,
        webhook_path: str = "/telegram-webhook",
        webhook_host: str = "127.0.0.1",
        webhook_port: int = 8787,
    ) -> None:
        super().__init__(
            client_name=client_name,
            client_json_path=client_json_path,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
            webhook_path=webhook_path,
            webhook_host=webhook_host,
            webhook_port=webhook_port,
        )
        
    def send_message(self, client_id: str, answer: str) -> tuple[str, str]:
        """
        Directly call the Telegram official API to send message.
        Here we assume that webhook_secret stores the Telegram Bot Token.
        """
        url = f"https://api.telegram.org/bot{self.webhook_secret}/sendMessage"
        payload = {
            "chat_id": client_id,
            "text": answer
        }
        
        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode('utf-8'), 
            headers={'Content-Type': 'application/json'}
        )
        
        try:
            with urllib.request.urlopen(req) as response:
                if response.getcode() == 200:
                    return self.client_name, "Message sent successfully"
                return self.client_name, f"HTTP Error: {response.getcode()}"
        except Exception as e:
            return self.client_name, f"Failed to send message: {str(e)}"