"""Create and use one webhook for Algorithm B.

Usage:
    Call `use_webhook()` to build one client webhook by channel.

Input spec:
    - `channel_name`: `telegram` or `feishu`.
    - `client_name`: one client name.
    - `client_json_path`: one client JSON path.
    - `webhook_url`: public webhook URL.
    - `webhook_secret`: shared webhook secret.

Output spec:
    - Returns a configured webhook instance.
"""

from webhooks.client_webhook import ClientWebhook
from webhooks.feishu_webhook import FeishuWebhook
from webhooks.telegram_webhook import TelegramWebhook


def use_webhook(
    channel_name: str,
    client_name: str,
    client_json_path: str,
    webhook_url: str,
    webhook_secret: str,
) -> ClientWebhook:
    assert channel_name in {"telegram", "feishu"}
    assert client_name
    assert client_json_path
    assert webhook_url
    assert webhook_secret

    if channel_name == "telegram":
        return TelegramWebhook(
            client_name=client_name,
            client_json_path=client_json_path,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
        )

    return FeishuWebhook(
        client_name=client_name,
        client_json_path=client_json_path,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
    )
