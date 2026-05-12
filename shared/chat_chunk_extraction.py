"""Extract chat messages from pre-stitched chat image chunks."""

from __future__ import annotations

from shared.datatypes import CapturedChatImages, ChatMessage
from shared.message_dedup import dedupe_chat_messages
from shared.message_time_window import (
    chunk_reaches_recent_cutoff,
    filter_messages_to_recent_window,
)
from shared.vision_prompts import CHAT_PANEL_PROMPT
from shared.vision_response_json import parse_json_object_from_model_text


def extract_messages_from_captured_chat(
    captured: CapturedChatImages,
    vision_ai,
    *,
    recent_window_hours: int = 0,
) -> list[ChatMessage]:
    """Run VLM extraction over already captured/stiched chat chunks."""
    all_messages: list[ChatMessage] = []
    chunk_results: list[tuple[int, list[ChatMessage]]] = []
    chunks = sorted(captured.chunks, key=lambda item: item.chunk_index, reverse=True)

    for chunk in chunks:
        display_index = chunk.chunk_index + 1
        print(f"--- Processing chunk {display_index}/{chunk.chunk_total} ---")
        try:
            response_str = vision_ai.query(
                CHAT_PANEL_PROMPT,
                chunk.image,
                max_tokens=16384,
            )
        except Exception as e:
            print(f"[ERROR] Vision AI query for chunk {display_index} failed: {e}")
            continue

        if not response_str:
            print(f"[ERROR] No response from AI for message extraction on chunk {display_index}.")
            continue

        try:
            data = parse_json_object_from_model_text(response_str)
            messages_data = data.get("messages", [])
        except Exception as e:
            print(f"[ERROR] Failed to parse messages from AI response for chunk {display_index}: {e}")
            print(f"Raw response was: {response_str}")
            continue

        chunk_messages: list[ChatMessage] = []
        for j, msg_data in enumerate(messages_data):
            if "content" not in msg_data:
                print(f"[WARN] Chunk {display_index}, Msg {j + 1}: Skipping message: {msg_data}")
                continue
            try:
                chunk_messages.append(ChatMessage(**msg_data))
            except TypeError as e:
                print(
                    f"[WARN] Chunk {display_index}, Msg {j + 1}: "
                    f"Skipping message during creation: {msg_data}. Error: {e}"
                )

        if not chunk_messages:
            print(f"[WARN] No valid messages extracted from chunk {display_index}.")
            continue

        filtered_chunk = filter_messages_to_recent_window(
            chunk_messages,
            hours=recent_window_hours,
        )
        print(f"[+] Extracted {len(chunk_messages)} messages from chunk {display_index}.")
        if filtered_chunk:
            chunk_results.append((chunk.chunk_index, filtered_chunk))
        if chunk_reaches_recent_cutoff(
            chunk_messages,
            hours=recent_window_hours,
        ):
            print(
                f"[*] Chunk {display_index} reached the {recent_window_hours}-hour cutoff. "
                "Skipping older chunks."
            )
            break

    chunk_results.sort(key=lambda item: item[0])
    for _, chunk_messages in chunk_results:
        all_messages.extend(chunk_messages)

    out = dedupe_chat_messages(all_messages)
    if (
        captured.max_messages is not None
        and captured.max_messages > 0
        and len(out) > captured.max_messages
    ):
        out = out[-captured.max_messages:]
    print(f"[*] Finished processing all chunks. Total messages: {len(out)} ({len(all_messages)} raw).")
    return out
