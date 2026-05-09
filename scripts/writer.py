"""Markdown assembly and output writer.

Adapted from srt_summarizer/processing/output_writer.py
"""

import os
import re
from datetime import datetime

from scripts._utils import sanitize_filename


IMAGE_SECTION_RE = re.compile(
    r"(^##\s+第[一二三四五六七八九十0-9]+部分.*?$)", re.MULTILINE
)
SUBSECTION_RE = re.compile(r"^###\s+.*?$|^####\s+.*?$", re.MULTILINE)
ANCHOR_RE = re.compile(r"\[\[插图(\d+)\]\]")
TOKEN_RE = re.compile(r"[A-Za-z0-9一-鿿]{2,}")



DATE_PATTERN = re.compile(r"^(\d{4})(\d{2})(\d{2})")


def _extract_date_label(filename: str) -> str:
    """Extract 'YYYY-MM-DD' from a filename starting with YYYYMMDD."""
    match = DATE_PATTERN.match(os.path.basename(filename))
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return ""


def build_output_paths(
    source_file: str,
    save_dir: str,
    course_name: str,
    lesson_title: str = "",
) -> tuple[str, str, str]:
    """Return (bundle_dir, image_dir, note_path).

    Output convention (per-lesson directory)::

        {课程名}/
        └── {课程目录名}/
            ├── {课程目录名}.md
            └── imgs/

    If *lesson_title* is provided, it is used as the bundle directory name
    and note filename. Otherwise, a name is auto-generated from the source
    file stem and course name.
    """
    if lesson_title:
        bundle_name = sanitize_filename(lesson_title, fallback="未命名课程")
        note_filename = f"{bundle_name}.md"
    else:
        stem = sanitize_filename(
            os.path.splitext(os.path.basename(source_file))[0], fallback="未命名文件"
        )
        course = sanitize_filename(course_name, fallback="未命名课程")
        bundle_name = f"{stem}_{course}"
        note_filename = f"{stem}_{course}_课堂总结.md"

    bundle_dir = os.path.join(save_dir, bundle_name)
    img_dir = os.path.join(bundle_dir, "imgs")
    note_path = os.path.join(bundle_dir, note_filename)
    return bundle_dir, img_dir, note_path


def normalize_markdown(content: str) -> str:
    """Remove excess blank lines, normalize line endings."""
    lines = [
        line.rstrip() for line in content.replace("\r\n", "\n").split("\n")
    ]
    cleaned: list[str] = []
    blank_run = 0
    for line in lines:
        if not line.strip():
            blank_run += 1
            if blank_run > 1:
                continue
            cleaned.append("")
            continue
        blank_run = 0
        cleaned.append(line)
    text = "\n".join(cleaned).strip()
    return text + "\n" if text else ""


# ---------------------------------------------------------------------------
# Image injection
# ---------------------------------------------------------------------------


def _normalize_match_text(text: str) -> str:
    text = re.sub(r"[（()）【】\[\]、，。；：！？,.!?:;\-_/]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.lower().strip()


def _extract_tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(_normalize_match_text(text))


def _split_markdown_sections(
    normalized: str,
) -> tuple[str, list[dict[str, str]]]:
    matches = list(IMAGE_SECTION_RE.finditer(normalized))
    if not matches:
        return normalized, []
    prefix = normalized[: matches[0].start()]
    sections: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(normalized)
        )
        block = normalized[start:end].strip()
        lines = block.splitlines()
        heading = lines[0].strip() if lines else ""
        body = "\n".join(lines[1:]).strip()
        subsection_lines = SUBSECTION_RE.findall(block)
        excerpt = body[:400]
        sections.append(
            {
                "heading": heading,
                "body": body,
                "block": block,
                "subsections": "\n".join(
                    line.strip() for line in subsection_lines
                ),
                "excerpt": excerpt,
            }
        )
    return prefix, sections


def _score_entry_against_section(
    entry: dict[str, str],
    section: dict[str, str],
    section_index: int,
    total_sections: int,
) -> float:
    snippet = str(entry.get("snippet", "")).strip()
    if not snippet:
        return 0.2 / max(abs(section_index), 1)
    snippet_tokens = _extract_tokens(snippet)
    if not snippet_tokens:
        return 0.0
    heading_text = _normalize_match_text(section["heading"])
    subsection_text = _normalize_match_text(section["subsections"])
    excerpt_text = _normalize_match_text(section["excerpt"])
    score = 0.0
    for token in snippet_tokens:
        if token in heading_text:
            score += 4.0
        if token in subsection_text:
            score += 3.0
        if token in excerpt_text:
            score += 1.2
    unique_count = len(set(snippet_tokens))
    if unique_count:
        score += min(unique_count * 0.1, 0.8)
    if total_sections > 1:
        expected_index = min(
            max(int(round((len(snippet_tokens) % total_sections))), 0),
            total_sections - 1,
        )
        score += max(0.0, 0.3 - abs(section_index - expected_index) * 0.08)
    return score


def _render_image_block(
    entry: dict[str, str], image_number: int, confidence: float
) -> str:
    rel_path = str(entry.get("relative_path", "")).replace("\\", "/")
    if not rel_path:
        return ""
    if str(entry.get("kind", "")).strip() == "diagram":
        title = str(entry.get("title", "")).strip()
        caption = str(entry.get("caption", "")).strip()
        alt = title or f"结构化图示 {image_number}"
        lines = [f"![{alt}]({rel_path})"]
        if caption:
            lines.append(f"> 图示说明：{caption}")
        return "\n".join(lines)
    lines = [f"![课堂截图 {image_number}]({rel_path})"]
    snippet = str(entry.get("snippet", "")).strip()
    timestamp = str(entry.get("timestamp", "")).strip()
    if confidence >= 4.5 and timestamp and not snippet:
        lines.append(f"> 看图提示：截图时间 {timestamp}")
    elif confidence >= 3.5 and snippet:
        helper = snippet.replace("\n", " ").strip()
        if len(helper) > 36:
            helper = helper[:36].rstrip() + "…"
        prefix = f"{timestamp} · " if timestamp else ""
        lines.append(f"> 看图提示：{prefix}{helper}")
    return "\n".join(lines)


def _build_appendix_block(
    entries: list[dict[str, str]], start_index: int
) -> str:
    if entries and str(entries[0].get("kind", "")).strip() == "diagram":
        title = "## 结构化图示补充"
    else:
        title = "## 课堂截图补充"
    lines = [title, ""]
    for image_number, entry in enumerate(entries, start=start_index):
        conf = 0.0
        if str(entry.get("snippet", "")).strip() and str(entry.get("timestamp", "")).strip():
            conf = 3.5
        elif str(entry.get("snippet", "")).strip() or str(entry.get("timestamp", "")).strip():
            conf = 2.0
        lines.append(
            _render_image_block(entry, image_number, confidence=conf)
        )
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _split_entry_kinds(
    entries: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    screenshots: list[dict[str, str]] = []
    diagrams: list[dict[str, str]] = []
    for entry in entries:
        if str(entry.get("kind", "")).strip() == "diagram":
            diagrams.append(entry)
        else:
            screenshots.append(entry)
    return screenshots, diagrams


def inject_images_into_markdown(
    content: str, image_entries: list[dict[str, str]]
) -> str:
    """Inject screenshots and diagrams into markdown body.

    Strategy:
    1. Replace [[插图N]] anchors with images (exact positions from LLM)
    2. Score remaining screenshots against markdown sections
    3. Append diagrams at the end
    """
    if not image_entries:
        return content

    screenshot_entries, diagram_entries = _split_entry_kinds(image_entries)
    next_image_number = 1
    anchored = content

    if screenshot_entries:
        # Phase 1: replace explicit anchors
        used_indices: set[int] = set()

        def repl(match: re.Match[str]) -> str:
            nonlocal next_image_number
            entry_index = int(match.group(1)) - 1
            if entry_index < 0 or entry_index >= len(screenshot_entries):
                return ""
            if entry_index in used_indices:
                return ""
            rendered = _render_image_block(
                screenshot_entries[entry_index], next_image_number, confidence=5.0
            )
            if not rendered:
                return ""
            used_indices.add(entry_index)
            next_image_number += 1
            return f"\n\n{rendered}\n\n"

        anchored = normalize_markdown(ANCHOR_RE.sub(repl, content))
        remaining = [
            entry
            for index, entry in enumerate(screenshot_entries)
            if index not in used_indices
        ]

        if remaining:
            prefix, sections = _split_markdown_sections(anchored)

            if not sections:
                appendix = _build_appendix_block(remaining, next_image_number)
                anchored = normalize_markdown(f"{anchored}\n{appendix}")
            else:
                # Score candidates
                candidates: list[dict] = []
                for entry_index, entry in enumerate(remaining):
                    for section_index, section in enumerate(sections):
                        score = _score_entry_against_section(
                            entry, section, section_index, len(sections)
                        )
                        if score <= 0:
                            continue
                        candidates.append(
                            {
                                "entry_index": entry_index,
                                "section_index": section_index,
                                "score": score,
                            }
                        )
                candidates.sort(key=lambda item: item["score"], reverse=True)

                max_per_section = 1 if len(remaining) <= len(sections) else 2
                assigned_entries: set[int] = set()
                section_counts = [0] * len(sections)
                section_images: list[
                    list[tuple[int, dict[str, str], float]]
                ] = [[] for _ in sections]
                appendix_entries: list[dict[str, str]] = []

                for candidate in candidates:
                    ei = candidate["entry_index"]
                    si = candidate["section_index"]
                    sc = candidate["score"]
                    if ei in assigned_entries:
                        continue
                    if sc < 2.6:
                        continue
                    if section_counts[si] >= max_per_section:
                        continue
                    section_images[si].append((ei, remaining[ei], sc))
                    section_counts[si] += 1
                    assigned_entries.add(ei)

                # Fallback: place remaining in content-rich sections
                strong_fallback = sorted(
                    range(len(sections)),
                    key=lambda idx: len(
                        _extract_tokens(
                            sections[idx]["heading"]
                            + " "
                            + sections[idx]["subsections"]
                            + " "
                            + sections[idx]["excerpt"]
                        )
                    ),
                    reverse=True,
                )
                for entry_index, entry in enumerate(remaining):
                    if entry_index in assigned_entries:
                        continue
                    placed = False
                    for section_index in strong_fallback:
                        if section_counts[section_index] >= max_per_section:
                            continue
                        if len(remaining) <= len(sections):
                            break
                        section_images[section_index].append(
                            (entry_index, entry, 0.0)
                        )
                        section_counts[section_index] += 1
                        assigned_entries.add(entry_index)
                        placed = True
                        break
                    if not placed:
                        appendix_entries.append(entry)

                # Rebuild
                built: list[str] = []
                if prefix.strip():
                    built.append(prefix.rstrip() + "\n\n")
                image_number = next_image_number
                for section_index, section in enumerate(sections):
                    built.append(section["block"].rstrip() + "\n")
                    if section_images[section_index]:
                        for _ei, entry, score in sorted(
                            section_images[section_index],
                            key=lambda item: item[0],
                        ):
                            built.append(
                                "\n"
                                + _render_image_block(entry, image_number, score)
                                + "\n"
                            )
                            image_number += 1
                if appendix_entries:
                    built.append(
                        "\n" + _build_appendix_block(appendix_entries, image_number)
                    )
                anchored = normalize_markdown("".join(built))
                next_image_number = image_number

    if diagram_entries:
        # Inject diagrams before ## 结构化图示输出 if present, otherwise append.
        # Never place content after the structured-diagram JSON block.
        json_section_re = re.compile(
            r"\n##\s+结构化图示输出\s*\n```json\b", re.MULTILINE
        )
        json_match = json_section_re.search(anchored)
        if json_match:
            diagram_block = _build_appendix_block(diagram_entries, next_image_number)
            anchored = (
                anchored[: json_match.start()]
                + "\n"
                + diagram_block
                + anchored[json_match.start() :]
            )
        else:
            diagram_block = _build_appendix_block(diagram_entries, next_image_number)
            anchored = normalize_markdown(f"{anchored}\n{diagram_block}")

    return anchored


def write_summary(
    out_path: str,
    source_path: str,
    content: str | None = None,
    image_entries: list[dict[str, str]] | None = None,
    now: datetime | None = None,
) -> None:
    """Write the final summary markdown file.

    If *content* is None / empty and *out_path* already exists,
    the existing file body is read and used as the content.
    """
    dt = now or datetime.now()
    date_label = _extract_date_label(source_path)

    if not content and os.path.isfile(out_path):
        with open(out_path, "r", encoding="utf-8") as f:
            existing = f.read()
        # Strip a previously-written header block if present
        existing = re.sub(r"^#[^\n]+\n\n>.*?---\n\n", "", existing, flags=re.DOTALL)
        existing = re.sub(r"^---\n.*?\n---\n\n", "", existing, flags=re.DOTALL)
        content = existing.strip()

    normalized = inject_images_into_markdown(content or "", image_entries or [])

    # Build YAML frontmatter — Obsidian-compatible, no #-heading before ## 一、课程概要
    frontmatter_lines = ["---"]
    if date_label:
        frontmatter_lines.append(f"date: {date_label}")
    frontmatter_lines.append(f"source: {os.path.basename(source_path)}")
    frontmatter_lines.append(f"generated: {dt.strftime('%Y-%m-%d')}")
    frontmatter_lines.append("---")
    frontmatter = "\n".join(frontmatter_lines) + "\n\n"

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(frontmatter)
        f.write(normalized)
