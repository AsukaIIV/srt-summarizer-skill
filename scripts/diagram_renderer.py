"""Structured diagram rendering for SRT summarizer skill.

Combines diagram spec parsing and PNG rendering.
Adapted from srt_summarizer/processing/diagram_specs.py and diagram_renderer.py

Requires Pillow (optional). When unavailable, diagram rendering is skipped.
"""

import json
import os
import re
from functools import lru_cache
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont  # type: ignore
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ---------------------------------------------------------------------------
# Diagram spec extraction
# ---------------------------------------------------------------------------

DIAGRAM_BLOCK_RE = re.compile(
    r"\n*##\s*结构化图示输出\s*\n+```json\s*(\{[\s\S]*?\})\s*```\s*$",
    re.MULTILINE,
)
ALLOWED_TYPES = {"comparison", "flow", "formula_map"}
MAX_DIAGRAMS = 2
MAX_ITEMS = 8
MAX_TEXT_LEN = 80


def _clean_text(value: Any, limit: int = MAX_TEXT_LEN) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit].strip()


def _clean_string_list(values: Any, limit: int = MAX_ITEMS) -> list[str]:
    if not isinstance(values, list):
        return []
    items: list[str] = []
    for value in values[:limit]:
        text = _clean_text(value)
        if text:
            items.append(text)
    return items


def _normalize_spec(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    diagram_type = _clean_text(raw.get("type"), limit=24).lower()
    if diagram_type not in ALLOWED_TYPES:
        return None
    title = _clean_text(raw.get("title"))
    if not title:
        return None
    summary = _clean_text(raw.get("summary"), limit=120)
    placement_hint = _clean_text(raw.get("placement_hint"), limit=120)
    spec: dict[str, Any] = {
        "type": diagram_type,
        "title": title,
        "summary": summary,
        "placement_hint": placement_hint,
    }
    if diagram_type == "comparison":
        left_title = _clean_text(raw.get("left_title"))
        right_title = _clean_text(raw.get("right_title"))
        left_items = _clean_string_list(raw.get("left_items"))
        right_items = _clean_string_list(raw.get("right_items"))
        if not left_title or not right_title or (not left_items and not right_items):
            return None
        spec.update(
            {
                "left_title": left_title,
                "right_title": right_title,
                "left_items": left_items,
                "right_items": right_items,
            }
        )
        return spec
    if diagram_type == "flow":
        steps = _clean_string_list(raw.get("steps"))
        if len(steps) < 2:
            return None
        spec["steps"] = steps
        return spec
    central_formula = _clean_text(raw.get("central_formula"), limit=120)
    branches = _clean_string_list(raw.get("branches"))
    if not central_formula or not branches:
        return None
    spec.update({"central_formula": central_formula, "branches": branches})
    return spec


def extract_diagram_specs(
    content: str,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Extract structured diagram JSON from LLM output.

    Returns (markdown_body, diagram_specs, warnings).
    """
    text = (content or "").strip()
    if not text:
        return "", [], []
    match = DIAGRAM_BLOCK_RE.search(text)
    if not match:
        return text, [], []
    markdown_body = text[: match.start()].rstrip()
    warnings: list[str] = []
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return markdown_body, [], ["结构化图示 JSON 解析失败，已跳过图示生成"]
    raw_specs = payload.get("diagrams") if isinstance(payload, dict) else None
    if not isinstance(raw_specs, list):
        return markdown_body, [], ["结构化图示格式无效，已跳过图示生成"]
    specs: list[dict[str, Any]] = []
    for index, raw_spec in enumerate(raw_specs[:MAX_DIAGRAMS], start=1):
        normalized = _normalize_spec(raw_spec)
        if normalized is None:
            warnings.append(f"第 {index} 个结构化图示格式无效，已跳过")
            continue
        specs.append(normalized)
    return markdown_body, specs, warnings


# ---------------------------------------------------------------------------
# Diagram PNG rendering  —  optimized visual templates
# ---------------------------------------------------------------------------

CANVAS_WIDTH = 1400

# ── colour palette ──────────────────────────────────────────────────────
_BG            = "#F8FAFC"   # page background
_CARD          = "#FFFFFF"
_TEXT          = "#1E293B"   # slate-800
_MUTED         = "#64748B"   # slate-500
_BORDER        = "#E2E8F0"   # slate-200

# per-type accent families
_CMP_A  = {"fill": "#EEF2FF", "head": "#6366F1", "dot": "#818CF8", "dark": "#4338CA"}  # indigo
_CMP_B  = {"fill": "#ECFDF5", "head": "#10B981", "dot": "#34D399", "dark": "#047857"}  # emerald
_FLOW   = ["#DBEAFE","#BFDBFE","#93C5FD","#60A5FA","#3B82F6","#2563EB"]
_FM_CTR = {"fill": "#FFFBEB", "border": "#F59E0B"}
_FM_BRN = ["#8B5CF6","#06B6D4","#F97316","#EC4899"]  # violet cyan orange pink

_LAST_FONT_SOURCE = "未初始化"


# ── helpers ─────────────────────────────────────────────────────────────

def _get_font_path() -> str:
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(skill_dir, "fonts", "HarmonyOS_Sans_SC_Medium.ttf")


@lru_cache(maxsize=16)
def _load_font(size: int, bold: bool = False) -> Any:
    global _LAST_FONT_SOURCE
    bundled = _get_font_path()
    candidates = [(bundled, "项目内字体")]
    if bold:
        candidates.extend([
            ("/System/Library/Fonts/PingFang.ttc", "系统字体"),
            ("C:/Windows/Fonts/msyhbd.ttc", "系统字体"),
            ("C:/Windows/Fonts/simhei.ttf", "系统字体"),
        ])
    candidates.extend([
        ("/System/Library/Fonts/PingFang.ttc", "系统字体"),
        ("/System/Library/Fonts/STHeiti Light.ttc", "系统字体"),
        ("C:/Windows/Fonts/msyh.ttc", "系统字体"),
        ("C:/Windows/Fonts/simhei.ttf", "系统字体"),
        ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", "系统字体"),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "系统字体"),
    ])
    for path, source_label in candidates:
        if os.path.exists(path):
            try:
                _LAST_FONT_SOURCE = f"{source_label}：{os.path.basename(path)}"
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    _LAST_FONT_SOURCE = "Pillow 默认字体"
    return ImageFont.load_default()


def get_last_font_source() -> str:
    return _LAST_FONT_SOURCE


def _measure(draw, text: str, font) -> tuple[int, int]:
    l, t, r, b = draw.multiline_textbbox((0, 0), text, font=font, spacing=6)
    return r - l, b - t


def _wrap_cjk(draw, text: str, font, max_w: int) -> str:
    if " " in text:
        return _wrap_en(draw, text, font, max_w)
    lines, cur = [], ""
    for ch in text:
        w, _ = _measure(draw, cur + ch, font)
        if cur and w > max_w:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def _wrap_en(draw, text: str, font, max_w: int) -> str:
    words = [s for s in text.replace("\n", " ").split(" ") if s]
    if not words:
        return ""
    lines, cur = [], words[0]
    for w in words[1:]:
        trial = f"{cur} {w}".strip()
        tw, _ = _measure(draw, trial, font)
        if tw <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return "\n".join(lines) if lines else cur


def _fit(draw, text: str, font, max_w: int) -> str:
    text = str(text or "").strip()
    if not text:
        return ""
    if any("一" <= ch <= "鿿" for ch in text) and " " not in text:
        return _wrap_cjk(draw, text, font, max_w)
    return _wrap_en(draw, text, font, max_w)


def _draw_shadow(draw, box, radius, colour=(0, 0, 0, 48), offset=(4, 6)):
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(
        (x1 + offset[0], y1 + offset[1], x2 + offset[0], y2 + offset[1]),
        radius=radius, fill=colour,
    )


def _draw_header_bar(draw, title: str, subtitle: str) -> int:
    """Draw page header with accent bar; return y after header."""
    # thin decorative line at top
    draw.rectangle((0, 0, CANVAS_WIDTH, 5), fill="#6366F1")
    tf = _load_font(38, bold=True)
    sf = _load_font(23)
    draw.text((80, 42), title, fill=_TEXT, font=tf)
    y_after = 98
    if subtitle:
        sub = _fit(draw, subtitle, sf, CANVAS_WIDTH - 160)
        draw.multiline_text((80, 104), sub, fill=_MUTED, font=sf, spacing=5)
        _, sh = _measure(draw, sub, sf)
        y_after = 110 + sh
    # separator line
    draw.line((80, y_after + 12, CANVAS_WIDTH - 80, y_after + 12), fill=_BORDER, width=2)
    return y_after + 38


def _card(
    draw, box, title, items, accent, item_prefix="",
    shadow_layer=None,
):
    """Draw a content card with coloured top accent strip & shadow."""
    x1, y1, x2, y2 = box
    r = 24
    if shadow_layer is not None:
        _draw_shadow(shadow_layer, box, r)
    # card body
    draw.rounded_rectangle(box, radius=r, fill=_CARD, outline=_BORDER, width=2)
    # coloured top accent inset strip (avoids interfering with card corner radius)
    accent_h = 10
    draw.rectangle((x1 + r, y1, x2 - r, y1 + accent_h), fill=accent["head"])
    # small coloured dot before title
    dot_r = 7
    dot_cx = x1 + r + 10
    dot_cy = y1 + accent_h + 26
    draw.ellipse(
        (dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r),
        fill=accent["head"],
    )
    # title
    tf = _load_font(26, bold=True)
    draw.text((dot_cx + dot_r + 14, dot_cy - 17), title, fill=accent["dark"], font=tf)
    # items
    bf = _load_font(22)
    cy = dot_cy + 34
    for item in items:
        prefix = item_prefix if item_prefix else "•"
        line = f"{prefix} {item}"
        wrapped = _fit(draw, line, bf, x2 - x1 - 64)
        _, h = _measure(draw, wrapped, bf)
        draw.multiline_text((x1 + 32, cy), wrapped, fill=_TEXT, font=bf, spacing=5)
        cy += h + 12
        if cy > y2 - 36:
            break


def _draw_vs_badge(draw, cx: int, cy: int, r: int = 36):
    """Draw a circular VS badge."""
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill="#F1F5F9", outline=_BORDER, width=3)
    tf = _load_font(22, bold=True)
    draw.text((cx - 18, cy - 14), "VS", fill=_MUTED, font=tf)


def _flow_step_number(draw, box, num: int, colour: str):
    """Draw a numbered circular badge."""
    x1, y1, x2, y2 = box
    r = (x2 - x1) // 2
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    draw.ellipse((x1, y1, x2, y2), fill=colour)
    bf = _load_font(22, bold=True)
    ts = str(num)
    tw, th = _measure(draw, ts, bf)
    draw.text((cx - tw // 2, cy - th // 2), ts, fill="#FFFFFF", font=bf)


def _connector_arrow(draw, x: int, y1: int, y2: int, colour: str):
    """Vertical connector: line + downward arrowhead."""
    draw.line((x, y1, x, y2), fill=colour, width=5)
    # arrowhead
    draw.polygon([(x, y2), (x - 14, y2 - 22), (x + 14, y2 - 22)], fill=colour)


# ── renderers ───────────────────────────────────────────────────────────

def _render_comparison(spec: dict[str, Any], out_path: str) -> dict[str, str]:
    H = 940
    # RGBA base for shadow compositing
    bg = Image.new("RGBA", (CANVAS_WIDTH, H), _BG + "FF")
    shadow = Image.new("RGBA", (CANVAS_WIDTH, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bg)
    sd = ImageDraw.Draw(shadow)

    after_hdr = _draw_header_bar(draw, spec["title"], spec.get("summary", ""))

    left_box  = (60,  after_hdr, 650, H - 50)
    right_box = (750, after_hdr, 1340, H - 50)

    _card(draw, left_box,  spec["left_title"],  spec.get("left_items", []),
          _CMP_A, item_prefix="", shadow_layer=sd)
    _card(draw, right_box, spec["right_title"], spec.get("right_items", []),
          _CMP_B, item_prefix="", shadow_layer=sd)

    # VS badge
    vs_y = after_hdr + (H - 50 - after_hdr) // 2
    _draw_vs_badge(draw, 700, vs_y)

    # composite shadow under cards
    out = Image.alpha_composite(bg, shadow).convert("RGB")
    out.save(out_path)
    return _make_entry(spec, out_path)


def _render_flow(spec: dict[str, Any], out_path: str) -> dict[str, str]:
    steps = spec.get("steps", [])[:6]
    n = len(steps)
    step_h = 104
    gap = 30
    body_top = 220
    body_h = n * step_h + (n - 1) * gap + 40
    H = body_top + body_h + 60

    bg = Image.new("RGBA", (CANVAS_WIDTH, H), _BG + "FF")
    shadow = Image.new("RGBA", (CANVAS_WIDTH, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bg)
    sd = ImageDraw.Draw(shadow)

    _draw_header_bar(draw, spec["title"], spec.get("summary", ""))

    timeline_x = 200
    card_x1 = 260
    card_x2 = 1320
    card_w = card_x2 - card_x1

    bf = _load_font(23)

    for i, step in enumerate(steps):
        idx = i
        y1 = body_top + i * (step_h + gap)
        y2 = y1 + step_h
        col = _FLOW[min(idx, len(_FLOW) - 1)]

        # card with shadow
        _draw_shadow(sd, (card_x1, y1, card_x2, y2), 20, offset=(3, 5))
        draw.rounded_rectangle(
            (card_x1, y1, card_x2, y2), radius=20,
            fill=_CARD, outline=_BORDER, width=2,
        )
        # left colour stripe
        draw.rectangle((card_x1, y1 + 16, card_x1 + 6, y2 - 16), fill=col)

        # step number circle
        circle_r = 26
        cx, cy = timeline_x, (y1 + y2) // 2
        draw.ellipse(
            (cx - circle_r, cy - circle_r, cx + circle_r, cy + circle_r),
            fill=col,
        )
        nf = _load_font(22, bold=True)
        ns = str(i + 1)
        nw, nh = _measure(draw, ns, nf)
        draw.text((cx - nw // 2, cy - nh // 2), ns, fill="#FFFFFF", font=nf)

        # step text
        wrapped = _fit(draw, step, bf, card_w - 80)
        tw, th = _measure(draw, wrapped, bf)
        draw.multiline_text(
            (card_x1 + 38, y1 + (step_h - th) // 2),
            wrapped, fill=_TEXT, font=bf, spacing=4,
        )

        # vertical connector line
        if i < n - 1:
            next_cy = body_top + (i + 1) * (step_h + gap) + step_h // 2
            draw.line((cx, cy + circle_r + 6, cx, next_cy - circle_r - 6),
                      fill=_BORDER, width=3)

    out = Image.alpha_composite(bg, shadow).convert("RGB")
    out.save(out_path)
    return _make_entry(spec, out_path)


def _render_formula_map(spec: dict[str, Any], out_path: str) -> dict[str, str]:
    H = 960
    bg = Image.new("RGBA", (CANVAS_WIDTH, H), _BG + "FF")
    shadow = Image.new("RGBA", (CANVAS_WIDTH, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bg)
    sd = ImageDraw.Draw(shadow)

    _draw_header_bar(draw, spec["title"], spec.get("summary", ""))

    # ── central formula card ──
    cbox = (350, 210, 1050, 410)
    _draw_shadow(sd, cbox, 28, offset=(3, 6))
    draw.rounded_rectangle(cbox, radius=28, fill=_FM_CTR["fill"],
                           outline=_FM_CTR["border"], width=4)
    ff = _load_font(32, bold=True)
    formula = _fit(draw, spec["central_formula"], ff, 620)
    fw, fh = _measure(draw, formula, ff)
    draw.multiline_text((700 - fw // 2, 310 - fh // 2), formula,
                        fill=_TEXT, font=ff, spacing=8)
    # tiny label
    lf = _load_font(18)
    draw.text((700 - 40, 375), "核心公式", fill=_FM_CTR["border"], font=lf)

    # ── branches ──
    branches = spec.get("branches", [])[:4]
    bboxes = [
        (60,  540, 620, 740),
        (780, 540, 1340, 740),
        (60,  770, 620, 900),
        (780, 770, 1340, 900),
    ]
    bf = _load_font(22)
    for i, (branch, bb) in enumerate(zip(branches, bboxes)):
        col = _FM_BRN[i]
        _draw_shadow(sd, bb, 20, offset=(2, 5))
        draw.rounded_rectangle(bb, radius=20, fill=_CARD, outline=_BORDER, width=2)
        # colour dot
        bx, by = bb[0] + 28, bb[1] + 28
        draw.ellipse((bx, by, bx + 18, by + 18), fill=col)
        wrapped = _fit(draw, branch, bf, bb[2] - bb[0] - 80)
        _, bh = _measure(draw, wrapped, bf)
        draw.multiline_text(
            (bx + 34, bb[1] + (bb[3] - bb[1] - bh) // 2),
            wrapped, fill=_TEXT, font=bf, spacing=5,
        )
        # connector from centre to branch
        s_y = cbox[3] + 20
        t_y = bb[1] - 16
        s_x = 700 if (bb[0] + bb[2]) // 2 < 700 else 700
        t_x = (bb[0] + bb[2]) // 2
        # rounded connector path
        mid_y = (s_y + t_y) // 2
        draw.line((s_x, s_y, s_x, mid_y, t_x, mid_y, t_x, t_y),
                  fill=col, width=4)
        draw.ellipse((t_x - 6, t_y - 6, t_x + 6, t_y + 6), fill=col)

    out = Image.alpha_composite(bg, shadow).convert("RGB")
    out.save(out_path)
    return _make_entry(spec, out_path)


def _make_entry(spec: dict[str, Any], out_path: str) -> dict[str, str]:
    return {
        "kind": "diagram",
        "relative_path": f"imgs/{os.path.basename(out_path)}",
        "title": spec["title"],
        "caption": spec.get("summary", "") or f"结构化图示：{spec['title']}",
        "snippet": spec.get("placement_hint", "") or spec["title"],
        "timestamp": "",
    }


# ── public entry ────────────────────────────────────────────────────────

def render_diagram_entries(
    diagram_specs: list[dict[str, Any]], image_dir: str
) -> tuple[list[dict[str, str]], list[str]]:
    """Render diagram specs to PNG images.

    Returns (entries, warnings).
    """
    if not HAS_PIL:
        return [], ["Pillow 未安装，跳过图示渲染。请运行: pip install Pillow"]

    if not diagram_specs:
        return [], []

    os.makedirs(image_dir, exist_ok=True)
    entries: list[dict[str, str]] = []
    warnings: list[str] = []
    for index, spec in enumerate(diagram_specs[:MAX_DIAGRAMS], start=1):
        out_path = os.path.join(image_dir, f"diagram_{index:02d}_{spec['type']}.png")
        try:
            if spec["type"] == "comparison":
                entry = _render_comparison(spec, out_path)
            elif spec["type"] == "flow":
                entry = _render_flow(spec, out_path)
            else:
                entry = _render_formula_map(spec, out_path)
            entries.append(entry)
        except (OSError, KeyError, ValueError) as exc:
            warnings.append(
                f"结构化图示《{spec.get('title', index)}》生成失败：{exc}"
            )
    return entries, warnings
