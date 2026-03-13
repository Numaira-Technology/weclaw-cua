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
import sys
import json
import urllib.request

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
        """
        接收从外层入口脚本（经过 sys.argv 解析后）传入的纯净数据。
        """
        assert client_id is not None
        assert client_question is not None
        
        return self.client_name, client_id, client_question

    def send_message(self, receiver_name: str, answer: str) -> tuple[str, str]:
        """
        Directly call the Telegram official API to reply to the message
        Here we assume that webhook_secret stores the Telegram Bot Token
        """
        url = f"https://api.telegram.org/bot{self.webhook_secret}/sendMessage"
        payload = {"client_name": receiver_name, "text": answer}
        
        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode('utf-8'), 
            headers={'Content-Type': 'application/json'}
        )
        
        try:
            urllib.request.urlopen(req)
            return self.client_name, "Success"
        except Exception as e:
            return self.client_name, f"Failed: {str(e)}"        
