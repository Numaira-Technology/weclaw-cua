"""Ranked context retrieval for captured chat messages.

Usage:
    from shared.chat_context import build_message_context, discover_message_json_paths
    paths = discover_message_json_paths("output", use_last_run=True)
    chunks = build_message_context("When is the meeting?", paths)

Input spec:
    - output_dir contains captured chat JSON files and optional last_run.json.
    - Message JSON files are arrays of objects with chat_name, sender, time, content, type.
    - question is the user's natural-language question.

Output spec:
    - discover_message_json_paths returns absolute JSON paths.
    - build_message_context returns ranked MessageContextChunk objects with cited messages.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass


@dataclass
class MessageContextChunk:
    chat: str
    source_path: str
    center_index: int
    score: float
    matched_terms: list[str]
    messages: list[dict]


TOKEN_RE = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]+", re.IGNORECASE)
CJK_RE = re.compile(r"^[\u4e00-\u9fff]+$")
METADATA_FILES = {"last_run.json", "last_check.json"}


def discover_message_json_paths(output_dir: str, *, use_last_run: bool = True) -> list[str]:
    assert output_dir
    output_dir = os.path.abspath(output_dir)
    manifest_path = os.path.join(output_dir, "last_run.json")
    if use_last_run and os.path.isfile(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        assert isinstance(manifest, dict)
        paths = manifest.get("message_json_paths", [])
        assert isinstance(paths, list)
        return [os.path.abspath(str(path)) for path in paths]

    assert os.path.isdir(output_dir), f"output directory not found: {output_dir}"
    names = [
        name for name in os.listdir(output_dir)
        if name.endswith(".json") and name not in METADATA_FILES and not name.startswith("last_")
    ]
    return [os.path.abspath(os.path.join(output_dir, name)) for name in sorted(names)]


def build_message_context(
    question: str,
    json_paths: list[str],
    *,
    top_k: int = 5,
    window: int = 2,
    chat_names: list[str] | None = None,
    msg_type: str | None = None,
) -> list[MessageContextChunk]:
    assert question.strip()
    assert top_k > 0
    assert window >= 0
    query_terms = _tokenize(question)
    candidates = _build_candidate_chunks(json_paths, window, chat_names or [], msg_type)
    if not candidates:
        return []

    document_frequency = Counter()
    for candidate in candidates:
        document_frequency.update(set(candidate["tokens"]))

    scored = []
    total = len(candidates)
    phrase = question.strip().lower()
    for candidate in candidates:
        score, matched_terms = _score_candidate(candidate, query_terms, phrase, document_frequency, total)
        if score > 0:
            scored.append((score, matched_terms, candidate))

    scored.sort(key=lambda item: (-item[0], item[2]["source_path"], item[2]["center_index"]))
    return _select_non_overlapping_chunks(scored, top_k, window)


def context_chunks_to_dicts(chunks: list[MessageContextChunk]) -> list[dict]:
    return [asdict(chunk) for chunk in chunks]


def _build_candidate_chunks(
    json_paths: list[str],
    window: int,
    chat_names: list[str],
    msg_type: str | None,
) -> list[dict]:
    lowered_chat_names = [name.lower() for name in chat_names]
    candidates = []
    for path in json_paths:
        messages = _load_message_file(path)
        for index, message in enumerate(messages):
            if msg_type and message.get("type") != msg_type:
                continue
            chat = str(message.get("chat_name") or os.path.splitext(os.path.basename(path))[0])
            if lowered_chat_names and not _chat_matches(chat, path, lowered_chat_names):
                continue
            start = max(0, index - window)
            end = min(len(messages), index + window + 1)
            chunk_messages = messages[start:end]
            text = _chunk_text(chunk_messages, chat, path)
            candidates.append(
                {
                    "chat": chat,
                    "source_path": os.path.abspath(path),
                    "center_index": index,
                    "messages": chunk_messages,
                    "text": text,
                    "tokens": Counter(_tokenize(text)),
                }
            )
    return candidates


def _load_message_file(path: str) -> list[dict]:
    assert os.path.isfile(path), f"message json not found: {path}"
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    assert isinstance(raw, list), f"Expected message list in {path}"
    assert all(isinstance(message, dict) for message in raw), f"Expected message objects in {path}"
    return raw


def _score_candidate(
    candidate: dict,
    query_terms: list[str],
    phrase: str,
    document_frequency: Counter,
    total_documents: int,
) -> tuple[float, list[str]]:
    score = 0.0
    matched_terms = []
    lowered_text = candidate["text"].lower()
    if phrase in lowered_text:
        score += 20.0
        matched_terms.append(phrase)

    unique_query_terms = list(dict.fromkeys(query_terms))
    for term in unique_query_terms:
        count = candidate["tokens"].get(term, 0)
        if not count:
            continue
        idf = math.log((1 + total_documents) / (1 + document_frequency[term])) + 1
        score += count * idf
        matched_terms.append(term)

    if unique_query_terms:
        coverage = len(set(matched_terms) & set(unique_query_terms)) / len(unique_query_terms)
        score *= 1.0 + coverage
        if coverage == 1.0:
            score += 5.0

    return score, list(dict.fromkeys(matched_terms))


def _select_non_overlapping_chunks(
    scored: list[tuple[float, list[str], dict]],
    top_k: int,
    window: int,
) -> list[MessageContextChunk]:
    selected: list[MessageContextChunk] = []
    for score, matched_terms, candidate in scored:
        overlaps = any(
            chunk.source_path == candidate["source_path"]
            and abs(chunk.center_index - candidate["center_index"]) <= window
            for chunk in selected
        )
        if overlaps:
            continue
        selected.append(
            MessageContextChunk(
                chat=candidate["chat"],
                source_path=candidate["source_path"],
                center_index=candidate["center_index"],
                score=round(score, 3),
                matched_terms=matched_terms,
                messages=candidate["messages"],
            )
        )
        if len(selected) >= top_k:
            break
    return selected


def _tokenize(text: str) -> list[str]:
    tokens = []
    for part in TOKEN_RE.findall(str(text or "").lower()):
        if CJK_RE.match(part):
            tokens.extend(_cjk_terms(part))
        elif len(part) >= 2:
            tokens.append(part)
    return tokens


def _cjk_terms(text: str) -> list[str]:
    terms = list(text)
    for size in (2, 3):
        terms.extend(text[index:index + size] for index in range(0, max(0, len(text) - size + 1)))
    return terms


def _chunk_text(messages: list[dict], chat: str, path: str) -> str:
    parts = [chat, os.path.basename(path)]
    for message in messages:
        parts.extend(
            [
                str(message.get("chat_name") or ""),
                str(message.get("sender") or ""),
                str(message.get("time") or ""),
                str(message.get("content") or ""),
                str(message.get("type") or ""),
            ]
        )
    return "\n".join(parts)


def _chat_matches(chat: str, path: str, lowered_chat_names: list[str]) -> bool:
    haystacks = [chat.lower(), os.path.splitext(os.path.basename(path))[0].lower()]
    return any(name in haystack for name in lowered_chat_names for haystack in haystacks)
