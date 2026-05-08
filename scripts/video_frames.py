"""Video frame extraction for SRT summarizer skill.

Adapted from srt_summarizer/processing/video_frames.py

Requires opencv-python (optional). When unavailable, extraction is skipped.
"""

import os
import sys
from datetime import datetime

from scripts._utils import format_seconds, sanitize_filename

try:
    import cv2  # type: ignore
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False



def _is_similar_frame(candidate_preview, selected_previews: list) -> bool:
    for preview in selected_previews:
        diff = abs(
            candidate_preview.astype("float32") - preview.astype("float32")
        ).mean()
        if diff < 12.0:
            return True
    return False


def _build_candidate_positions(frame_count: int, candidate_count: int) -> list[int]:
    if frame_count <= 0:
        return []
    start = max(int(frame_count * 0.05), 0)
    end = min(int(frame_count * 0.95), max(frame_count - 1, 0))
    if end <= start:
        start, end = 0, max(frame_count - 1, 0)
    if candidate_count <= 1 or end <= start:
        return [start]
    step = (end - start) / max(candidate_count - 1, 1)
    positions: list[int] = []
    seen: set[int] = set()
    for index in range(candidate_count):
        pos = min(max(int(round(start + index * step)), 0), max(frame_count - 1, 0))
        if pos in seen:
            continue
        seen.add(pos)
        positions.append(pos)
    return positions


def _build_subtitle_positions(
    segments: list[dict], fps: float, frame_count: int, max_frames: int
) -> list[int]:
    if not segments or fps <= 0:
        return []
    picked: list[int] = []
    seen: set[int] = set()
    sorted_segments = sorted(
        (
            segment
            for segment in segments
            if isinstance(segment.get("text"), str)
            and len(str(segment.get("text", "")).strip()) >= 6
            and float(segment.get("end_seconds", 0))
            > float(segment.get("start_seconds", 0))
        ),
        key=lambda item: float(item.get("start_seconds", 0)),
    )
    if not sorted_segments:
        return []
    stride = max(len(sorted_segments) // max(max_frames * 3, 1), 1)
    for index, segment in enumerate(sorted_segments[::stride]):
        if len(picked) >= max(max_frames * 6, 18):
            break
        start_seconds = float(segment["start_seconds"])
        end_seconds = float(segment["end_seconds"])
        midpoint = start_seconds + (end_seconds - start_seconds) / 2
        position = min(max(int(round(midpoint * fps)), 0), max(frame_count - 1, 0))
        if position in seen:
            continue
        seen.add(position)
        picked.append(position)
    return picked


def _score_frame(frame) -> tuple:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    brightness = float(gray.mean())
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    edges = cv2.Canny(gray, 80, 160)
    edge_density = float((edges > 0).mean())
    downsampled = cv2.resize(gray, (64, 36))

    score = 0.0
    if 25 <= brightness <= 235:
        score += 2.0
    elif 15 <= brightness <= 245:
        score += 1.0
    score += min(blur / 120.0, 3.0)
    score += min(edge_density * 12.0, 3.0)
    return score, {"brightness": brightness, "blur": blur, "edge_density": edge_density}, downsampled


def _select_best_candidates(
    candidates: list[dict], max_frames: int, allow_low_quality: bool = False
) -> list[dict]:
    selected: list[dict] = []
    for candidate in sorted(candidates, key=lambda item: item["score"], reverse=True):
        metrics = candidate["metrics"]
        if not allow_low_quality:
            if metrics["brightness"] < 20 or metrics["brightness"] > 240:
                continue
            if metrics["blur"] < 40:
                continue
            if metrics["edge_density"] < 0.01:
                continue
        if _is_similar_frame(candidate["preview"], [s["preview"] for s in selected]):
            continue
        selected.append(candidate)
        if len(selected) >= max_frames:
            break
    return sorted(selected, key=lambda item: item["position"])



def _build_image_filename(
    course_name: str, sequence: int, identifier: str, now: datetime | None = None
) -> str:
    dt = now or datetime.now()
    date_part = dt.strftime("%Y%m%d")
    course_part = sanitize_filename(course_name)
    id_part = sanitize_filename(identifier)
    return f"{date_part}_{course_part}_{sequence:03d}_{id_part}.png"


def _find_related_segment(segments: list[dict], seconds: float) -> dict | None:
    if not segments:
        return None
    best_segment = None
    best_distance = None
    for segment in segments:
        start_seconds = float(segment.get("start_seconds", 0))
        end_seconds = float(segment.get("end_seconds", 0))
        if start_seconds <= seconds <= end_seconds:
            return segment
        midpoint = start_seconds + max(end_seconds - start_seconds, 0) / 2
        distance = abs(midpoint - seconds)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_segment = segment
    return best_segment


def extract_frames(
    video_path: str,
    image_dir: str,
    max_frames: int = 8,
    subtitle_segments: list[dict] | None = None,
    course_name: str = "",
) -> tuple[list[str], list[dict]]:
    """Extract high-quality screenshots from a video.

    Returns (saved_paths, frame_items) where each frame_item has:
        path, timestamp, snippet

    Raises RuntimeError if video cannot be opened or no valid frames found.
    """
    if not HAS_CV2:
        raise RuntimeError(
            "opencv-python 未安装。请运行: pip install opencv-python"
        )

    if not video_path:
        return [], []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频：{video_path}")

    try:
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if frame_count <= 0:
            return [], []

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        max_frames = max(1, min(max_frames, 20))
        candidate_count = min(max(max_frames * 8, 24), 120)
        candidates: list[dict] = []

        normalized_segments = subtitle_segments or []
        positions: list[int] = []
        seen_positions: set[int] = set()

        subtitle_positions = _build_subtitle_positions(
            normalized_segments, fps, frame_count, max_frames
        )
        for position in subtitle_positions:
            if position in seen_positions:
                continue
            positions.append(position)
            seen_positions.add(position)

        if len(positions) < candidate_count:
            extra_positions = _build_candidate_positions(frame_count, candidate_count)
            for position in extra_positions:
                if position in seen_positions:
                    continue
                positions.append(position)
                seen_positions.add(position)

        for position in positions:
            cap.set(cv2.CAP_PROP_POS_FRAMES, position)
            ok, frame = cap.read()
            if not ok:
                continue
            score, metrics, preview = _score_frame(frame)
            candidates.append(
                {
                    "position": position,
                    "frame": frame,
                    "score": score,
                    "metrics": metrics,
                    "preview": preview,
                    "timestamp_id": format_seconds(
                        position / fps if fps > 0 else 0.0, include_ms=True
                    ).replace(":", "-").replace(".", "-"),
                }
            )

        if not candidates:
            raise RuntimeError("无法提取截图：未能从视频读取到任何帧")

        selected = _select_best_candidates(candidates, max_frames)
        if len(selected) < max_frames:
            seen_positions_sel = {item["position"] for item in selected}
            relaxed_pool = [
                item for item in candidates if item["position"] not in seen_positions_sel
            ]
            selected.extend(
                _select_best_candidates(
                    relaxed_pool, max_frames - len(selected), allow_low_quality=True
                )
            )
            selected = sorted(selected, key=lambda item: item["position"])

        if not selected:
            raise RuntimeError(
                "无法提取有效截图：读取到了视频帧，但都未通过有效性筛选"
            )

        os.makedirs(image_dir, exist_ok=True)
        saved: list[str] = []
        for index, candidate in enumerate(selected, start=1):
            identifier = candidate.get("timestamp_id") or f"frame-{candidate.get('position', index)}"
            out_path = os.path.join(
                image_dir,
                _build_image_filename(course_name, index, str(identifier)),
            )
            ext = os.path.splitext(out_path)[1] or ".png"
            ok, encoded = cv2.imencode(ext, candidate["frame"])
            if not ok:
                continue
            try:
                encoded.tofile(out_path)
            except OSError as exc:
                print(
                    f"[WARNING] 截图写入失败：{out_path} — {exc}",
                    file=sys.stderr,
                )
                continue
            saved.append(out_path)

        frame_items: list[dict] = []
        for path, candidate in zip(saved, selected):
            seconds = candidate["position"] / fps if fps > 0 else 0.0
            segment = _find_related_segment(normalized_segments, seconds)
            snippet = ""
            if segment:
                snippet = (
                    str(segment.get("text", "")).strip().replace("\n", " ")[:80]
                )
            frame_items.append(
                {
                    "path": path,
                    "timestamp": format_seconds(seconds, include_ms=True),
                    "snippet": snippet,
                }
            )

        return saved, frame_items
    finally:
        cap.release()
