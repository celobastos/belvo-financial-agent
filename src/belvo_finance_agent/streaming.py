from __future__ import annotations

import time
from collections.abc import Iterator


def chunk_text(text: str, chunk_size: int = 12) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    return [text[index : index + chunk_size] for index in range(0, len(text), chunk_size)] or [""]


def stream_text(text: str, delay: float = 0.01, chunk_size: int = 12) -> Iterator[str]:
    for chunk in chunk_text(text, chunk_size=chunk_size):
        if delay:
            time.sleep(delay)
        yield chunk


def enable_streaming(eval_mode: bool = False, configured: bool = True) -> bool:
    return configured and not eval_mode
