"""Telegram webhook for one client.

Usage:
    Use this class directly or inherit it for a client-specific Telegram hook.

Input spec:
    - Same inputs as `ClientWebhook`.

Output spec:
    - Returns a configured Telegram webhook instance.
"""

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
