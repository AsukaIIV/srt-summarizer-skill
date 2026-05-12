"""File scanner and lesson pairing.

Adapted from srt_summarizer/processing/file_scanner.py and lesson_pairing.py
"""

import os
import re
from datetime import datetime

SUPPORTED_EXT = (".srt", ".txt", ".md")
SUPPORTED_VIDEO_EXT = (".mp4", ".mkv", ".mov", ".avi", ".m4v")

NOISE_TOKENS = {
    "1080p", "720p", "2160p", "avc", "hevc", "x264", "x265",
    "h264", "h265", "字幕", "subtitle", "sub", "chs", "cht", "eng", "aac",
}

# Filename pattern: YYYYMMDD_HHMMSS.xxx
_DATETIME_RE = re.compile(r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})")
# Note filename pattern: YYYY-MM-DD_xxx.md
_NOTE_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


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


# ---------------------------------------------------------------------------
# Course context: match transcript → course → previous notes
# ---------------------------------------------------------------------------

def _extract_datetime(filename: str) -> datetime | None:
    """Extract datetime from filename like 20260331_080425."""
    basename = os.path.basename(filename)
    m = _DATETIME_RE.search(basename)
    if not m:
        return None
    return datetime(*map(int, m.groups()))


def _extract_note_date(filename: str) -> str:
    """Extract date string from a note filename, handling both formats:
    '2026-03-31_xxx.md' and '20260331_xxx.md'.
    """
    # Format 1: YYYY-MM-DD
    m = _NOTE_DATE_RE.search(filename)
    if m:
        return m.group(1)
    # Format 2: YYYYMMDD
    m2 = re.search(r"(\d{4})(\d{2})(\d{2})", filename)
    if m2:
        return f"{m2.group(1)}-{m2.group(2)}-{m2.group(3)}"
    return ""


def _parse_note_date(filename: str) -> datetime | None:
    """Parse a note filename into a datetime, or None."""
    date_str = _extract_note_date(filename)
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None


def _scan_course_notes(output_base: str) -> dict[str, list[dict]]:
    """Scan output directory for all course → notes mappings.

    Returns {course_name: [{path, date, mtime, dt}, ...]} sorted by mtime desc.
    """
    courses: dict[str, list[dict]] = {}
    if not os.path.isdir(output_base):
        return courses

    for course_name in sorted(os.listdir(output_base)):
        course_dir = os.path.join(output_base, course_name)
        if not os.path.isdir(course_dir):
            continue
        notes: list[dict] = []
        for root, _, files in os.walk(course_dir):
            for fn in files:
                if not fn.endswith(".md"):
                    continue
                full = os.path.join(root, fn)
                mtime = os.path.getmtime(full)
                note_date = _extract_note_date(fn)
                note_dt = _parse_note_date(fn)
                notes.append({
                    "path": full,
                    "filename": fn,
                    "date": note_date,
                    "dt": note_dt,
                    "mtime": mtime,
                })
        notes.sort(key=lambda n: n["mtime"], reverse=True)
        courses[course_name] = notes
    return courses


def find_course_context(
    transcript_path: str,
    output_base: str = ".",
    max_notes: int = 2,
) -> dict:
    """Match a transcript to its course and fetch previous notes for context.

    Matching strategy:
      1. Same weekday + same hour-of-day → highest confidence
      2. Same weekday only
      3. Nearest date proximity across all courses

    Returns {
        "course_name": str or "",
        "matched_by": "weekday_hour" | "weekday" | "proximity" | "none",
        "context_notes": [{path, filename, date}, ...],
        "all_courses": [str, ...],        # for user to choose if no match
    }
    """
    result: dict = {
        "course_name": "",
        "matched_by": "none",
        "context_notes": [],
        "all_courses": [],
    }

    transcript_dt = _extract_datetime(transcript_path)
    courses = _scan_course_notes(output_base)
    result["all_courses"] = sorted(courses.keys())

    if not courses:
        return result

    if transcript_dt is None:
        # Cannot match by date — return all course names for manual selection
        return result

    weekday = transcript_dt.weekday()  # 0=Mon
    hour = transcript_dt.hour

    # Score each course
    scores: list[tuple[str, float, str]] = []  # (course, score, match_type)
    for course_name, notes in courses.items():
        course_dates = [
            datetime.strptime(n["date"], "%Y-%m-%d")
            for n in notes[:10]
            if n["date"]
        ]
        if not course_dates:
            continue

        # Check weekday pattern
        course_weekdays = {d.weekday() for d in course_dates}
        course_hours: set[int] = set()
        for n in notes[:10]:
            nm = _DATETIME_RE.search(n.get("filename", ""))
            if nm:
                course_hours.add(int(nm.group(4)))

        score = 0.0
        match_type = "proximity"

        if weekday in course_weekdays and hour in course_hours:
            score = 10.0
            match_type = "weekday_hour"
        elif weekday in course_weekdays:
            score = 6.0
            match_type = "weekday"
        else:
            # Proximity: distance to nearest note
            min_dist = min(
                abs((transcript_dt - d).days) for d in course_dates
            )
            score = max(0.0, 4.0 - min_dist * 0.1)
            match_type = "proximity"

        scores.append((course_name, score, match_type))

    if not scores:
        return result

    scores.sort(key=lambda s: s[1], reverse=True)
    best_course, best_score, match_type = scores[0]

    if best_score < 3.0:
        # Too weak — ambiguous match, let user decide
        return result

    result["course_name"] = best_course
    result["matched_by"] = match_type

    # Fetch recent notes strictly BEFORE the transcript date
    prior_notes = [
        n for n in courses[best_course]
        if n["dt"] and n["dt"].date() < transcript_dt.date()
    ]
    result["context_notes"] = prior_notes[:max_notes]

    return result


def load_context_content(context_notes: list[dict]) -> str:
    """Read the content of context notes and return a condensed summary.

    Each note: strip YAML frontmatter, return first ~3000 chars of body.
    """
    blocks: list[str] = []
    for note in context_notes:
        try:
            with open(note["path"], "r", encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        # Strip YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            content = parts[2] if len(parts) > 2 else content
        # Take first section headers + body for condensed context
        lines = content.strip().split("\n")
        # Keep up to ~200 lines as context
        condensed = "\n".join(lines[:200])
        label = f"📘 {note.get('date', '未知日期')} — {note.get('filename', '')}"
        blocks.append(f"### {label}\n\n{condensed}")
    return "\n\n---\n\n".join(blocks)
