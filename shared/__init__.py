from shared.message_schema import Message, messages_from_json, messages_to_json
from shared.platform_api import PlatformDriver

__all__ = [
    "Message",
    "PlatformDriver",
    "call_llm",
    "messages_from_json",
    "messages_to_json",
]


def __getattr__(name: str):
    if name == "call_llm":
        from shared.llm_client import call_llm

        return call_llm
    raise AttributeError(f"module 'shared' has no attribute {name!r}")
