"""Sample entry point script triggered by adnanh/webhook.

Brief description:
    Parse CLI arguments coming from adnanh/webhook (or local testing) and
    call the Algorithm B pipeline via a webhook abstraction.

Usage:
    Local testing:
        python3 sample_run_pipeline.py telegram 12345678 "今天群里有什么新闻？"

    With webhook:
        curl -X POST http://localhost:9000/hooks/telegram-hook \\
            -H "Content-Type: application/json" \\
            -d '{"message": {"chat": {"id": "<client id>"}, "text": "你好，这是本地模拟测试！"}}'

Input spec:
    - argv[1]: platform name (for example, "telegram").
    - argv[2]: sender/client id.
    - argv[3]: message text.

Output spec:
    - Exit code 0 on success.
    - Non-zero exit code if arguments are missing or the pipeline crashes.
"""
import os
import sys
import logging
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from algorithm_b.use_webhook import use_webhook


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def run_pipeline(platform: str, sender_id: str, text: str) -> None:
    logging.info(
        "Received request -> Platform: %s | User: %s | Text: %s",
        platform,
        sender_id,
        text,
    )

    client_name = "test_customer"
    client_json_path = f"./data/{client_name}.json"

    webhook_url = os.getenv("TELEGRAM_WEBHOOK_URL")
    webhook_secret = os.getenv("TELEGRAM_BOT_TOKEN")
    assert webhook_url, "TELEGRAM_WEBHOOK_URL must be set in environment"
    assert webhook_secret, "TELEGRAM_BOT_TOKEN must be set in environment"

    hook = use_webhook(
        channel_name=platform,
        client_name=client_name,
        client_json_path=client_json_path,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
    )

    client_name_resolved, clean_sender_id, clean_text = hook.receive_message(
        sender_id,
        text,
    )
    assert client_name_resolved == client_name

    if not clean_text.strip():
        logging.warning("Received an empty message. Aborting.")
        sys.exit(0)

    logging.info("Running Algorithm B Pipeline (Mocked)...")
    answer = f"[Mock Answer] 收到你的提问：'{clean_text}'。这是自动回复。"
    logging.info("Algorithm B output: %s", answer)

    status_name, status_msg = hook.send_message(clean_sender_id, answer)
    logging.info("Send Delivery Status -> %s: %s", status_name, status_msg)


def main() -> None:
    if len(sys.argv) < 4:
        logging.error(
            "Missing arguments! Expected: python3 sample_run_pipeline.py <platform> <sender_id> <text>",
        )
        sys.exit(1)

    try:
        run_pipeline(
            platform=sys.argv[1],
            sender_id=sys.argv[2],
            text=sys.argv[3],
        )
    except Exception as e:
        logging.error(f"Pipeline crashed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()