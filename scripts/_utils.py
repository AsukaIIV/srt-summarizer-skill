"""Shared utilities for the SRT summarizer skill scripts."""

import re


def format_seconds(seconds: float, include_ms: bool = False) -> str:
    """Format seconds to HH:MM:SS or HH:MM:SS.mmm."""
    total_ms = max(int(round(seconds * 1000)), 0)
    hours = total_ms // 3600000
    minutes = (total_ms % 3600000) // 60000
    secs = (total_ms % 60000) // 1000
    if include_ms:
        millis = total_ms % 1000
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def sanitize_filename(value: str, fallback: str = "unnamed") -> str:
    """Sanitize a string for use as a filename component."""
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", str(value).strip()).strip(".")
    return cleaned or fallback
