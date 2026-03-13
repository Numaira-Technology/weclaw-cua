"""
Sample entry point script triggered by adnanh/webhook.

Local Testing Usage:
    python3 sample_run_pipeline.py telegram 12345678 "今天群里有什么新闻？"
command line usage:
    curl -X POST http://localhost:9000/hooks/telegram-hook -H "Content-Type: application/json" -d '{"message": {"chat": {"id": "<client id>"},"text": "你好，这是本地模拟测试！"}}'
"""

import os
import sys
import logging
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from algorithm_b.use_webhook import use_webhook
# from algorithm_b.pipeline_b import run_single_question

# 设置日志格式，方便在终端查看执行进度
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    # 
    if len(sys.argv) < 4:
        logging.error("Missing arguments! Expected: python3 sample_run_pipeline.py <platform> <sender_id> <text>")
        sys.exit(1)

    # 2. 从环境(sys.argv)中提取业务数据
    platform = sys.argv[1]    # e.g., "telegram"
    sender_id = sys.argv[2]   # e.g., "12345678"
    text = sys.argv[3]        # e.g., "你好"
    
    logging.info(f"Received request -> Platform: {platform} | User: {sender_id} | Text: {text}")

    # 3. 初始化相关配置 (在实际生产中，这些可以写在 config.json 或环境变量里)
    client_name = "test_customer"
    client_json_path = f"./data/{client_name}.json"

    webhook_url = os.getenv("TELEGRAM_WEBHOOK_URL")
    webhook_secret = os.getenv("TELEGRAM_BOT_TOKEN")
    assert webhook_url, "TELEGRAM_WEBHOOK_URL must be set in environment"
    assert webhook_secret, "TELEGRAM_BOT_TOKEN must be set in environment"
    
    # 4. 根据平台名称，实例化对应的 Webhook 类
    hook = use_webhook(
        channel_name=platform,
        client_name=client_name,
        client_json_path=client_json_path,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
    )

    # 5. 调用 receive_message 格式化数据
    client_name, clean_sender_id, clean_text = hook.receive_message(sender_id, text)
    
    if not clean_text.strip():
        logging.warning("Received an empty message. Aborting.")
        sys.exit(0)

    try:
        # 6. 调用 Algorithm B (Pipeline) 生成回答
        # 在真实环境中，取消下面代码的注释并提供所需的文件路径:
        """
        answer = run_single_question(
            mapping_path="./data/mapping.json",
            main_store_path="./data/main_store.json",
            output_dir="./data/output",
            customer_name=client_name,
            question=clean_text
        )
        """
        
        # 本地测试用的 Mock Answer:
        logging.info("Running Algorithm B Pipeline (Mocked)...")
        answer = f"[Mock Answer] 收到你的提问：'{clean_text}'。这是自动回复。"
        logging.info(f"Algorithm B output: {answer}")
        
        # 7. 主动通过 HTTP 将答案发回给平台
        status_name, status_msg = hook.send_message(clean_sender_id, answer)
        logging.info(f"Send Delivery Status -> {status_name}: {status_msg}")
        
    except Exception as e:
        logging.error(f"Pipeline crashed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()