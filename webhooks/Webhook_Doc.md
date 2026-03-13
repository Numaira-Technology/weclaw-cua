## 1. Install dependencies

- Install `webhook`:
  - `brew install webhook`
- Install `ngrok` (to expose local port 9000 to the internet):
  - `brew install ngrok/ngrok/ngrok`

## 2. Basic webhook concept

- `webhook` listens on local port `9000` by default, and its default route prefix is `/hooks/`.
- In `webhooks/hooks.json`, config for telegram has been set up `"id": "telegram-hook"`.
- So the actual URL called by Telegram is:
  - `http://<server-ip>:9000/hooks/telegram-hook`
  - If exposed via ngrok, it will look like: `https://xxxx.ngrok-free.dev/hooks/telegram-hook`

## 3. Important fields in hooks.json

- `execute-command`: **absolute path to the Python interpreter**, not the script path  
  For example: `/usr/bin/python3` or the Python in your virtualenv.
- `command-working-directory`: working directory when running the script  
- With the current config, `webhook` will run:
  - `python3 sample_run_pipeline.py telegram <chat_id> <text>`

## 4. Environment variables

- Create and edit `.env` in the **project root** (already in `.gitignore`, so it will not be committed to Git):

  ```bash
  TELEGRAM_WEBHOOK_URL=<your public webhook url, e.g. https://xxxx.ngrok-free.dev/hooks/telegram-hook>
  TELEGRAM_BOT_TOKEN=<your Telegram Bot Token>
  ```

- Load environment variables in the terminal:

  ```bash
  source .env
  ```

## 5. Local testing

### 5.1 Run the Python script directly

```bash
python3 webhooks/sample_run_pipeline.py telegram <chat_id> "Hello"
```

### 5.2 Use webhook + curl to simulate a Telegram call

1. Start the `webhook` service (in the `webhooks` directory):

   ```bash
   webhook -hooks hooks.json -verbose
   # (optional) expose local port 9000 to the internet
   ngrok http 9000  # run this in another terminal; you will get a public URL like https://xxxx.ngrok-free.app
   ```

2. To test locally, use curl to simulate a Telegram message:

    ```
    curl -X POST http://localhost:9000/hooks/telegram-hook \
    -H "Content-Type: application/json" \
    -d '{
        "message": {
        "chat": {"id": "<chat_id>"},
        "text": "Hello, this is a local test!"
        }
    }'
3. If you are using ngrok, bind your Telegram webhook to the public URL:
    ```
    https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=https://<NGROK_URL>/hooks/telegram-hook
    ```

4. Check the terminal logs to confirm that sample_run_pipeline.py was triggered and that the Telegram Bot sent a reply successfully.