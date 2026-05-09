"""qa-context command — retrieve ranked message context for answering questions.

Usage:
    weclaw qa-context "When is tomorrow's meeting?"
    weclaw qa-context "Who needs a reply?" --all-history --chat "Team"

Input spec:
    - Reads last_run.json message_json_paths by default.
    - With --all-history, reads captured chat JSON files in output_dir.
    - Question is natural language and may include Chinese or English terms.

Output spec:
    - JSON contains ranked chunks with source_path, chat, center_index, score, matched_terms, messages.
    - Text contains the same cited snippets in human-readable form.
"""

import os

import click

from shared.chat_context import build_message_context
from shared.chat_context import context_chunks_to_dicts
from shared.chat_context import discover_message_json_paths
from ..output.formatter import output


@click.command("qa-context")
@click.argument("question")
@click.option("--chat", multiple=True, help="Limit to specific chat(s)")
@click.option("--limit", default=5, help="Max context chunks (max 50)")
@click.option("--window", default=2, help="Messages before and after each hit")
@click.option("--all-history", is_flag=True, help="Search all exports instead of only last_run.json paths")
@click.option("--format", "fmt", default="json",
              type=click.Choice(["json", "text"]),
              help="Output format")
@click.option("--type", "msg_type", default=None,
              type=click.Choice(["text", "system", "link_card", "image", "file", "recalled", "unsupported"]),
              help="Filter center messages by type")
@click.pass_context
def qa_context(ctx, question, chat, limit, window, all_history, fmt, msg_type):
    """Return ranked message snippets for agent Q&A.

    \b
    Examples:
      weclaw qa-context "明天中午客户会几点？"
      weclaw qa-context "Who mentioned approval?" --all-history
      weclaw qa-context "deadline" --chat "Project Alpha" --format text
    """
    from ..context import load_app_context

    assert limit > 0
    assert limit <= 50
    assert window >= 0

    app = load_app_context(ctx)
    paths = discover_message_json_paths(app["output_dir"], use_last_run=not all_history)
    chunks = build_message_context(
        question,
        paths,
        top_k=limit,
        window=window,
        chat_names=list(chat),
        msg_type=msg_type,
    )
    result = {
        "question": question,
        "scope": "all history" if all_history else "last run",
        "context_method": "ranked lexical chunks over captured message files",
        "answer_instructions": "Answer only from these cited messages; if they are insufficient, say what is missing.",
        "source_files": paths,
        "chat": list(chat),
        "type": msg_type,
        "count": len(chunks),
        "limit": limit,
        "window": window,
        "chunks": context_chunks_to_dicts(chunks),
    }

    if fmt == "json":
        output(result, "json")
        return

    output(_format_text(result), "text")


def _format_text(result: dict) -> str:
    lines = [
        f'Q&A context for "{result["question"]}" ({result["count"]} chunks, scope={result["scope"]})',
        result["answer_instructions"],
    ]
    if not result["chunks"]:
        lines.append("No matching context found.")
        return "\n".join(lines)

    for index, chunk in enumerate(result["chunks"], start=1):
        source = os.path.basename(chunk["source_path"])
        lines.append(
            f'[{index}] score={chunk["score"]} chat={chunk["chat"]} source={source} '
            f'center_index={chunk["center_index"]} matched={", ".join(chunk["matched_terms"])}'
        )
        for message in chunk["messages"]:
            sender = message.get("sender") or "?"
            time = message.get("time") or "时间未知"
            content = message.get("content") or ""
            mtype = message.get("type") or "text"
            tag = f" [{mtype}]" if mtype != "text" else ""
            lines.append(f"  - {time} | {sender}{tag}: {content}")
    return "\n".join(lines)
