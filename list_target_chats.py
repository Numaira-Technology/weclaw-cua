
import json
from typing import List

def load_target_chats(config_path: str = "config.json") -> List[str]:
    """
    Loads the list of target chat names from the config file.

    Args:
        config_path: Path to the JSON configuration file.

    Returns:
        A list of chat names to be monitored.
    """
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            return config.get("monitored_chats", [])
    except FileNotFoundError:
        print(f"[ERROR] Config file not found at: {config_path}")
        return []
    except json.JSONDecodeError:
        print(f"[ERROR] Could not decode JSON from: {config_path}")
        return []

if __name__ == "__main__":
    # This is for standalone testing of this module
    target_chats = load_target_chats()
    if target_chats:
        print("[+] Successfully loaded target chats:")
        for chat in target_chats:
            print(f"  - {chat}")
    else:
        print("[!] No target chats loaded. Check your config.json or the file path.")

