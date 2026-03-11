"""Base webhook class for one client.

Usage:
    Inherit this class or use a channel-specific subclass.

Input spec:
    - `client_name`: one client name.
    - `client_json_path`: one client JSON path.
    - `webhook_url`: public webhook URL.
    - `webhook_secret`: shared webhook secret.
    - `webhook_path`: local webhook path.
    - `webhook_host`: local webhook host.
    - `webhook_port`: local webhook port.

Output spec:
    - `endpoint_config()` returns endpoint settings.
    - `receive_message()` returns `(client_name, message)`.
    - `send_message()` returns `(client_name, message)`.
"""


class ClientWebhook:
    channel_name: str = ""

    def __init__(
        self,
        client_name: str,
        client_json_path: str,
        webhook_url: str,
        webhook_secret: str,
        webhook_path: str,
        webhook_host: str,
        webhook_port: int,
    ) -> None:
        assert self.channel_name
        assert client_name
        assert client_json_path
        assert webhook_url
        assert webhook_secret
        assert webhook_path
        assert webhook_host
        assert webhook_port > 0

        self.client_name = client_name
        self.client_json_path = client_json_path
        self.webhook_url = webhook_url
        self.webhook_secret = webhook_secret
        self.webhook_path = webhook_path
        self.webhook_host = webhook_host
        self.webhook_port = webhook_port

    def endpoint_config(self) -> dict[str, str | int]:
        return {
            "channel_name": self.channel_name,
            "client_name": self.client_name,
            "client_json_path": self.client_json_path,
            "webhook_url": self.webhook_url,
            "webhook_secret": self.webhook_secret,
            "webhook_path": self.webhook_path,
            "webhook_host": self.webhook_host,
            "webhook_port": self.webhook_port,
        }

    def receive_message(self, message: str) -> tuple[str, str]:
        assert message
        return self.client_name, message

    def send_message(self, message: str) -> tuple[str, str]:
        assert message
        return self.client_name, message
