"""File scanner and lesson pairing.

Adapted from srt_summarizer/processing/file_scanner.py and lesson_pairing.py
"""

import os
import re

SUPPORTED_EXT = (".srt", ".txt", ".md")
SUPPORTED_VIDEO_EXT = (".mp4", ".mkv", ".mov", ".avi", ".m4v")

NOISE_TOKENS = {
    "1080p", "720p", "2160p", "avc", "hevc", "x264", "x265",
    "h264", "h265", "字幕", "subtitle", "sub", "chs", "cht", "eng", "aac",
}


def scan_transcripts(directory: str) -> list[str]:
    """Scan a directory recursively for supported transcript files."""
    found: list[str] = []
    for root, _, files in os.walk(directory):
        for fn in sorted(files):
            if fn.lower().endswith(SUPPORTED_EXT):
                found.append(os.path.join(root, fn))
    return found


def scan_videos(directory: str) -> list[str]:
    """Scan a directory recursively for video files."""
    found: list[str] = []
    for root, _, files in os.walk(directory):
        for fn in sorted(files):
            if fn.lower().endswith(SUPPORTED_VIDEO_EXT):
                found.append(os.path.join(root, fn))
    return found


def _normalize_name(path: str) -> str:
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    stem = re.sub(r"[\[\](){}._\-]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    tokens = [
        token for token in stem.split() if token and token not in NOISE_TOKENS
    ]
    return " ".join(tokens)


def _score_match(transcript_path: str, video_path: str) -> float:
    transcript_tokens = set(_normalize_name(transcript_path).split())
    video_tokens = set(_normalize_name(video_path).split())
    if not transcript_tokens or not video_tokens:
        return 0.0
    overlap = transcript_tokens & video_tokens
    union = transcript_tokens | video_tokens
    score = len(overlap) / max(len(union), 1)
    transcript_stem = os.path.splitext(os.path.basename(transcript_path))[0].lower()
    video_stem = os.path.splitext(os.path.basename(video_path))[0].lower()
    if transcript_stem in video_stem or video_stem in transcript_stem:
        score += 0.2
    return score


def _match_video(
    transcript_path: str,
    video_paths: list[str],
    exact_map: dict[str, str],
    normalized_map: dict[str, str],
) -> str:
    stem = os.path.splitext(os.path.basename(transcript_path))[0]
    exact = exact_map.get(stem.lower(), "")
    if exact:
        return exact
    normalized_name = _normalize_name(transcript_path)
    normalized = normalized_map.get(normalized_name, "")
    if normalized:
        return normalized
    scored = sorted(
        ((path, _score_match(transcript_path, path)) for path in video_paths),
        key=lambda item: item[1],
        reverse=True,
    )
    if not scored:
        return ""
    best_path, best_score = scored[0]
    second_score = scored[1][1] if len(scored) > 1 else 0.0
    if best_score >= 0.45 and best_score - second_score >= 0.1:
        return best_path
    return ""


def pair_lessons(
    transcript_paths: list[str], video_paths: list[str]
) -> list[dict]:
    """Pair transcript files with video files.

    Returns a list of dicts with keys:
        lesson_id, transcript_path, video_path, source_label
    """
    videos_by_stem = {
        os.path.splitext(os.path.basename(path))[0].lower(): path
        for path in video_paths
    }
    videos_by_normalized = {
        _normalize_name(path): path
        for path in video_paths
        if _normalize_name(path)
    }

    lessons: list[dict] = []
    for transcript_path in transcript_paths:
        stem = os.path.splitext(os.path.basename(transcript_path))[0]
        lessons.append(
            {
                "lesson_id": transcript_path,
                "transcript_path": transcript_path,
                "video_path": _match_video(
                    transcript_path, video_paths, videos_by_stem, videos_by_normalized
                ),
                "source_label": stem,
            }
        )
    return lessons


def scan_and_pair(target: str) -> dict:
    """Scan a directory or file and return a summary.

    Returns a dict with:
        transcripts: list of transcript file paths
        videos: list of video file paths
        lessons: list of paired dicts
        is_directory: bool
    """
    if os.path.isdir(target):
        transcripts = scan_transcripts(target)
        videos = scan_videos(target)
        lessons = pair_lessons(transcripts, videos)
        return {
            "transcripts": transcripts,
            "videos": videos,
            "lessons": lessons,
            "is_directory": True,
            "directory": target,
        }
    elif os.path.isfile(target):
        ext = target.lower()
        is_transcript = ext.endswith(SUPPORTED_EXT)
        parent_dir = os.path.dirname(target) or "."
        videos = scan_videos(parent_dir) if is_transcript else []
        lessons = (
            [
                {
                    "lesson_id": target,
                    "transcript_path": target,
                    "video_path": _match_video(
                        target,
                        videos,
                        {
                            os.path.splitext(os.path.basename(p))[0].lower(): p
                            for p in videos
                        },
                        {
                            _normalize_name(p): p
                            for p in videos
                            if _normalize_name(p)
                        },
                    ),
                    "source_label": os.path.splitext(os.path.basename(target))[0],
                }
            ]
            if is_transcript
            else []
        )
        return {
            "transcripts": [target] if is_transcript else [],
            "videos": videos,
            "lessons": lessons,
            "is_directory": False,
            "directory": parent_dir,
        }
    else:
        raise FileNotFoundError(f"路径不存在：{target}")
