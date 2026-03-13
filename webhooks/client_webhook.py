"""Base webhook class for one client.

Usage:
    Subclass this class for each concrete channel (for example, Telegram or Feishu)
    and implement channel-specific message sending in `send_message`.

Input spec:
    - `client_name`: logical name of the client.
    - `client_json_path`: path to client-specific configuration JSON.
    - `webhook_url`: public webhook URL visible to the external platform.
    - `webhook_secret`: shared secret or token used for authentication.
    - `webhook_path`: local webhook HTTP path.
    - `webhook_host`: local webhook host.
    - `webhook_port`: local webhook port.

Output spec:
    - `endpoint_config()`: mapping of endpoint configuration fields.
    - `receive_message()`: tuple `(client_name, client_id, question)`.
    - `send_message()`: must be implemented by subclasses and return a
      tuple `(client_name, status)`.
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

    def receive_message(self, client_id: str, client_question: str) -> tuple[str, str, str]:
        assert client_id is not None
        assert client_question is not None
        return self.client_name, client_id, client_question

    def send_message(self, receiver_name: str, answer: str) -> tuple[str, str]:
        msg = (
            f"{self.__class__.__name__}.send_message() is not implemented. "
            "Use a concrete channel subclass instead."
        )
        raise NotImplementedError(msg)
