"""Token-bounded Markdown chunks and their preceding context."""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Literal

import tiktoken


CHUNKING_VERSION = "page-header-v3"
MIN_CONTENT_TOKENS = 20


@dataclass(frozen=True)
class ChunkDraft:
    sequence: int
    page_number: int
    chunk_type: Literal["para", "table"]
    heading_path: list[str]
    content: str
    overlap_text: str
    token_count: int


_encoding = tiktoken.get_encoding("cl100k_base")


def _tokens(value: str) -> list[int]:
    return _encoding.encode(value)


def _decode(tokens: list[int]) -> str:
    return _encoding.decode(tokens)


def _with_context(draft: ChunkDraft, previous: str, sequence: int, overlap_tokens: int) -> ChunkDraft:
    overlap = _decode(_tokens(previous)[-overlap_tokens:]) if previous and overlap_tokens else ""
    combined = "\n".join(value for value in (
        " > ".join(draft.heading_path), overlap, draft.content
    ) if value)
    return replace(draft, sequence=sequence, overlap_text=overlap, token_count=len(_tokens(combined)))


def _merge_short_chunks(drafts: list[ChunkDraft], max_tokens: int, overlap_tokens: int) -> list[ChunkDraft]:
    """Merge short content forward, retaining the destination's metadata.

    Rebuild context from retained content only, including for chunks after a
    merge. Leave a short chunk alone if there is no successor or no room.
    """
    merged: list[ChunkDraft] = []
    index = 0
    while index < len(drafts):
        current = drafts[index]
        previous = merged[-1].content if merged else ""
        while len(_tokens(current.content)) < MIN_CONTENT_TOKENS and index + 1 < len(drafts):
            following = drafts[index + 1]
            candidate = replace(following, content=f"{current.content}\n\n{following.content}")
            candidate = _with_context(candidate, previous, len(merged), overlap_tokens)
            if candidate.token_count > max_tokens:
                break
            current = candidate
            index += 1
        merged.append(_with_context(current, previous, len(merged), overlap_tokens))
        index += 1
    return merged


def _split_to_limit(content: str, heading_prefix: str, available: int) -> list[str]:
    tokens = _tokens(content)
    if len(tokens) <= available:
        return [content.strip()]
    return [_decode(tokens[index:index + available]).strip() for index in range(0, len(tokens), available)]


def _split_table_to_limit(content: str, available: int) -> list[str]:
    if len(_tokens(content)) <= available:
        return [content.strip()]
    if content.lstrip().lower().startswith("<table"):
        opening = re.search(r"<table[^>]*>", content, re.IGNORECASE)
        rows = re.findall(r"<tr[^>]*>.*?</tr>", content, re.IGNORECASE | re.DOTALL)
        if opening and rows:
            header = rows[0] if "<th" in rows[0].lower() else ""
            parts: list[str] = []
            current = [opening.group(0), header] if header else [opening.group(0)]
            for row in rows[1:] if header else rows:
                candidate = "\n".join(current + [row, "</table>"])
                if len(_tokens(candidate)) > available and len(current) > (2 if header else 1):
                    parts.append("\n".join(current + ["</table>"]))
                    current = [opening.group(0), header, row] if header else [opening.group(0), row]
                else:
                    current.append(row)
            if len(current) > 1:
                parts.append("\n".join(current + ["</table>"]))
            if parts and all(len(_tokens(part)) <= available for part in parts):
                return parts
    else:
        lines = content.splitlines()
        if len(lines) >= 3:
            header = lines[:2]
            parts, current = [], header.copy()
            for row in lines[2:]:
                candidate = "\n".join(current + [row])
                if len(_tokens(candidate)) > available and len(current) > 2:
                    parts.append("\n".join(current))
                    current = header + [row]
                else:
                    current.append(row)
            if len(current) > 2:
                parts.append("\n".join(current))
            if parts and all(len(_tokens(part)) <= available for part in parts):
                return parts
    return _split_to_limit(content, "", available)


def chunk_markdown(markdown: str, max_tokens: int = 2000, overlap_tokens: int = 50) -> list[ChunkDraft]:
    if max_tokens <= overlap_tokens:
        raise ValueError("max_tokens must be greater than overlap_tokens")
    headings: list[str] = []
    blocks: list[tuple[str, list[str], str, int]] = []
    paragraph: list[str] = []
    table: list[str] = []
    html_table = False
    page_number = 1

    def flush_paragraph():
        if paragraph:
            blocks.append(("para", headings.copy(), "\n".join(paragraph).strip(), page_number))
            paragraph.clear()

    def flush_table():
        if table:
            blocks.append(("table", headings.copy(), "\n".join(table).strip(), page_number))
            table.clear()

    for line in markdown.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        stripped = line.strip()
        starts_html_table = bool(re.match(r"<table(?:\s|>)", stripped, re.IGNORECASE))
        is_pipe_table = line.lstrip().startswith("|") and line.rstrip().endswith("|")
        if re.fullmatch(r"<!--\s*PageBreak\s*-->", stripped, re.IGNORECASE):
            flush_paragraph(); flush_table()
            html_table = False
            page_number += 1
        elif html_table or starts_html_table:
            if not html_table:
                flush_paragraph()
                html_table = True
            table.append(line)
            if re.search(r"</table>\s*$", stripped, re.IGNORECASE):
                html_table = False
                flush_table()
        elif heading:
            flush_paragraph(); flush_table()
            level = len(heading.group(1))
            headings[:] = headings[: level - 1]
            headings.append(heading.group(2).strip())
        elif is_pipe_table:
            flush_paragraph(); table.append(line)
        elif not stripped:
            flush_table()
            if paragraph and paragraph[-1] != "":
                paragraph.append("")
        else:
            flush_table(); paragraph.append(line)
    flush_paragraph(); flush_table()

    drafts: list[ChunkDraft] = []
    previous_original = ""
    for chunk_type, path, block, block_page in blocks:
        prefix = " > ".join(path)
        # Reserve the full overlap budget for every continuation; later pieces
        # overlap their immediate predecessor rather than the prior block.
        reserved = len(_tokens(prefix)) + overlap_tokens + 2
        available = max(1, max_tokens - reserved)
        parts = _split_table_to_limit(block, available) if chunk_type == "table" else _split_to_limit(block, prefix, available)
        for part in parts:
            part_overlap = _decode(_tokens(previous_original)[-overlap_tokens:]) if previous_original and overlap_tokens else ""
            combined = "\n".join(value for value in (prefix, part_overlap, part) if value)
            drafts.append(ChunkDraft(
                sequence=len(drafts), page_number=block_page,
                chunk_type=chunk_type, heading_path=path.copy(),
                content=part, overlap_text=part_overlap, token_count=len(_tokens(combined)),
            ))
            previous_original = part
    return _merge_short_chunks(drafts, max_tokens, overlap_tokens)
