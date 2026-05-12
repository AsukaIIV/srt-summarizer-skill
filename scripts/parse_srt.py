"""SRT subtitle parsing and quality assessment.

Adapted from srt_summarizer/processing/file_loader.py
"""

import os
import re
from dataclasses import dataclass, field

from scripts._utils import format_seconds

SRT_TIME_RE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2}[,.]\d{3})"
)

# ---- Domain classification patterns ----

STEM_KEYWORDS: set[str] = {
    "数学", "物理", "化学", "电路", "电子", "信号", "通信",
    "编程", "算法", "计算机", "工程", "力学", "光学", "电磁",
    "量子", "微积分", "线性代数", "概率论", "代码", "方程",
    "公式", "推导", "半导体", "晶体管", "放大器", "滤波器",
    "调制", "解调", "傅里叶", "拉普拉斯", "微分", "积分",
    "数据结构", "操作系统", "网络协议", "编译原理", "体系结构",
}

SOCIAL_SCIENCE_KEYWORDS: set[str] = {
    "历史", "哲学", "政治", "经济", "社会", "管理", "法律",
    "心理", "教育", "文学", "艺术", "文化", "伦理", "马克思",
    "毛概", "思修", "概论", "思想", "制度", "政策", "国际关系",
    "社会学", "经济学", "法学", "行政", "组织行为", "公共管理",
    "近代史", "思想政治", "道德", "法治", "治理",
}

# ---- Quality assessment patterns ----

# Characters that suggest encoding corruption
GARBLED_CHAR_RE = re.compile(r"[�\x00-\x08\x0b\x0c\x0e-\x1f]")

# ASR filler / hesitation markers (English + Chinese)
FILLER_RE = re.compile(
    r"\b(um|uh|er|ah|mm|hmm|erm|uhh|umm)\b|呃+|嗯+|啊(?!的|呀|吧|吗|哪)|这个这个|那个那个|然后然后|就是就是|就是说|怎么说呢",
    re.IGNORECASE,
)

# Repeated word/character patterns (stutter / ASR loop).
# True ASR stutter occurs with zero or whitespace-only gap between repeats.
# We deliberately avoid flexible separators to prevent false positives
# from legitimate word recurrence in coherent text.
REPEATED_WORD_RE = re.compile(
    r"([一-鿿]{2,})\s*\1"  # CJK: "那个那个", "波函数 波函数"
    r"|\b(\w{3,})\b\s+\1\b"               # Latin: "wave wave"
)

# Lines dominated by non-semantic content.
# Either no CJK at all (pure symbols/numbers), or symbols exceed 60% of chars.
NOISE_LINE_RE = re.compile(r"^[^一-鿿]{4,}$")
NOISE_SYMBOL_RATIO = 0.6  # if >60% chars are non-alphanumeric, treat as noise

# Chinese-specific: unusual ratio of latin chars may indicate mixed encoding
LATIN_IN_CJK_RE = re.compile(r"[a-zA-Z]{10,}")

# Segments that end/start mid-sentence (no punctuation)
MID_SENTENCE_END_RE = re.compile(r"[^。！？.!?…‥…」】』\"'）\)]$")



@dataclass
class QualityReport:
    """Structured quality assessment for a transcript."""

    overall_score: int = 100  # 0-100
    level: str = "good"       # "good" | "medium" | "poor"

    total_segments: int = 0
    garbled_segments: list[int] = field(default_factory=list)
    mid_sentence_segments: list[int] = field(default_factory=list)
    filler_segments: list[int] = field(default_factory=list)
    repeated_segments: list[int] = field(default_factory=list)
    noise_segments: list[int] = field(default_factory=list)
    short_segments: list[int] = field(default_factory=list)
    long_segments: list[int] = field(default_factory=list)

    avg_text_len: float = 0.0
    avg_duration: float = 0.0

    # Human-readable flags
    flags: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """One-line quality summary."""
        emoji = {"good": "✓", "medium": "⚠", "poor": "✗"}
        return (
            f"{emoji.get(self.level, '?')} 字幕质量：{self.level} "
            f"(评分 {self.overall_score}/100)"
        )

    def markdown(self) -> str:
        """Structured quality report in Markdown for inclusion in the prompt."""
        if self.level == "good" and not self.flags:
            return ""
        lines = [
            "## 字幕质量评估报告",
            "",
            f"**综合评分**：{self.overall_score}/100（{self.level}）",
            "",
        ]
        if self.flags:
            lines.append("**发现的问题**：")
            for flag in self.flags:
                lines.append(f"- {flag}")
            lines.append("")
        if self.details:
            lines.append("**详细说明**：")
            for detail in self.details:
                lines.append(f"- {detail}")
            lines.append("")
        return "\n".join(lines)


def assess_quality(segments: list[dict]) -> QualityReport:
    """Analyze subtitle segments and produce a quality report.

    Checks for:
    - Garbled/encoding-corrupted text
    - Mid-sentence breaks (ASR splitting issues)
    - Filler words and hesitation markers
    - Repeated words (ASR stutter loops)
    - Pure noise lines
    - Unusual segment durations
    - Text density extremes
    """
    report = QualityReport(total_segments=len(segments))

    if not segments:
        report.overall_score = 0
        report.level = "poor"
        report.flags.append("无有效字幕段")
        return report

    # Per-segment analysis
    text_lengths: list[int] = []
    durations: list[float] = []
    total_chars = 0
    cjk_chars = 0

    for i, seg in enumerate(segments, start=1):
        text = seg.get("text", "")
        duration = float(seg.get("end_seconds", 0)) - float(seg.get("start_seconds", 0))
        text_lengths.append(len(text))
        durations.append(duration)
        total_chars += len(text)
        cjk_chars += sum(1 for ch in text if "一" <= ch <= "鿿")

        # Garbled characters
        if GARBLED_CHAR_RE.search(text):
            report.garbled_segments.append(i)

        # Mid-sentence breaks
        if MID_SENTENCE_END_RE.search(text.rstrip()):
            report.mid_sentence_segments.append(i)

        # Filler-heavy
        fillers = FILLER_RE.findall(text)
        if len(fillers) >= 2:
            report.filler_segments.append(i)

        # Repeated words (Latin or CJK stutter)
        if REPEATED_WORD_RE.search(text):
            report.repeated_segments.append(i)

        # Pure noise line (no CJK at all, or symbol-dominated)
        stripped = text.strip()
        if NOISE_LINE_RE.match(stripped):
            report.noise_segments.append(i)
        elif len(stripped) >= 4:
            alpha_cjk = sum(1 for ch in stripped if ch.isalpha() or "一" <= ch <= "鿿")
            if alpha_cjk / len(stripped) < (1 - NOISE_SYMBOL_RATIO):
                report.noise_segments.append(i)

        # Duration anomalies
        if duration < 0.3:
            report.short_segments.append(i)
        if duration > 30.0:
            report.long_segments.append(i)

    # Aggregate statistics
    report.avg_text_len = sum(text_lengths) / len(text_lengths)
    report.avg_duration = sum(durations) / len(durations)

    total = len(segments)

    # Score deduction — use proportional penalties instead of binary thresholds
    score = 100.0
    deductions: list[tuple[int, str]] = []

    # 1. Garbled chars — proportional (0..30 pts)
    garbled_pct = len(report.garbled_segments) / total
    if garbled_pct > 0:
        penalty = min(round(garbled_pct * 300), 30)
        score -= penalty
        deductions.append((penalty, f"{len(report.garbled_segments)}/{total} 段含乱码字符 ({garbled_pct:.1%})"))

    # 2. Mid-sentence endings — raw ASR output is nearly 100%, recalibrated
    mid_pct = len(report.mid_sentence_segments) / total
    if mid_pct >= 0.95:
        # Typical raw ASR output — expected, but still harder to work with
        score -= 10
        deductions.append((10, f"几乎全部段不以标点结尾（{mid_pct:.0%}），典型的 ASR 无标点输出"))
    elif mid_pct > 0.6:
        score -= 18
        deductions.append((18, f"{len(report.mid_sentence_segments)}/{total} 段不以标点结尾（{mid_pct:.0%}），断句问题严重"))
    elif mid_pct > 0.3:
        score -= 10
        deductions.append((10, f"{len(report.mid_sentence_segments)}/{total} 段不以标点结尾（{mid_pct:.0%}），断句可能不准确"))

    # 3. Filler words — proportional (0..12 pts)
    filler_pct = len(report.filler_segments) / total
    if filler_pct > 0:
        penalty = min(round(filler_pct * 60), 12)
        score -= penalty
        deductions.append((penalty, f"{len(report.filler_segments)}/{total} 段含较多语气词填充"))

    # 4. Repeated words / stutter — proportional (0..12 pts)
    repeat_pct = len(report.repeated_segments) / total
    if repeat_pct > 0:
        penalty = min(round(repeat_pct * 80), 12)
        score -= penalty
        deductions.append((penalty, f"{len(report.repeated_segments)}/{total} 段含重复词或卡顿"))

    # 5. Pure noise lines — proportional (0..20 pts)
    noise_pct = len(report.noise_segments) / total
    if noise_pct > 0:
        penalty = min(round(noise_pct * 400), 20)
        score -= penalty
        deductions.append((penalty, f"{len(report.noise_segments)}/{total} 段疑似纯噪音"))

    # 6. Duration anomalies — proportional (0..10 pts)
    short_pct = len(report.short_segments) / total
    if short_pct > 0:
        penalty = min(round(short_pct * 50), 10)
        score -= penalty
        deductions.append((penalty, f"{len(report.short_segments)}/{total} 段时长过短（<0.3s），可能为碎片化识别"))

    # 7. Text density — continuous penalty
    if report.avg_text_len < 5:
        penalty = 18
        deductions.append((penalty, f"平均每段仅 {report.avg_text_len:.0f} 字符，内容极度稀疏"))
    elif report.avg_text_len < 8:
        penalty = 12
        deductions.append((penalty, f"平均每段 {report.avg_text_len:.0f} 字符，内容稀疏，信息密度低"))
    elif report.avg_text_len < 12:
        penalty = 6
        deductions.append((penalty, f"平均每段 {report.avg_text_len:.0f} 字符，内容偏稀疏"))
    else:
        penalty = 0

    score -= penalty

    # 8. Chinese character ratio (ASR on Chinese courses should be mostly CJK)
    cjk_ratio = cjk_chars / max(total_chars, 1)
    if cjk_ratio < 0.3 and total_chars > 100:
        penalty = round((0.3 - cjk_ratio) * 40)
        score -= penalty
        deductions.append((penalty, f"中文字符占比仅 {cjk_ratio:.0%}，可能含大量编码污染或非中文内容"))

    # 9. Content repetition (detect duplicated segments beyond ASR stutter)
    if len(segments) >= 10:
        text_samples = [seg.get("text", "").strip() for seg in segments if len(seg.get("text", "").strip()) >= 4]
        if len(text_samples) >= 10:
            unique_ratio = len(set(text_samples)) / len(text_samples)
            if unique_ratio < 0.7:
                penalty = round((0.7 - unique_ratio) * 80)
                score -= penalty
                deductions.append((penalty, f"内容重复率高，仅 {unique_ratio:.0%} 唯一段"))

    # Round score
    report.overall_score = max(0, min(100, int(round(score))))

    # Build flags and details from deductions (sorted by severity)
    deductions.sort(key=lambda x: x[0], reverse=True)
    for deducted, msg in deductions:
        report.flags.append(msg)

    # Detailed per-segment issue listing (capped)
    if report.garbled_segments:
        examples = report.garbled_segments[:5]
        seg_texts = [
            f"#{n}: {segments[n-1].get('text', '')[:60]}…" for n in examples
        ]
        report.details.append(
            f"乱码段示例（共{len(report.garbled_segments)}段）：{'；'.join(seg_texts)}"
        )

    if report.mid_sentence_segments and mid_pct >= 0.95:
        report.details.append(
            f"字幕几乎全部无标点结尾（{mid_pct:.0%}），这是 ASR 引擎的典型输出特征。"
            f"生成笔记时请自行推断句间边界，跨段拼接完整语义。"
        )
    elif report.mid_sentence_segments and mid_pct > 0.5:
        report.details.append(
            f"超过半数字幕段不以句末标点结束（{mid_pct:.0%}），"
            f"可能是 ASR 按时间窗口切分导致句子被截断，请特别注意跨段拼接语义"
        )

    if report.filler_segments:
        report.details.append(
            f"含较多口语填充词（um/uh/呃/嗯），建议忽略这些词，提取实质内容"
        )

    if report.overall_score >= 80:
        report.level = "good"
    elif report.overall_score >= 50:
        report.level = "medium"
    else:
        report.level = "poor"

    return report


def quality_guidance(report: QualityReport) -> str:
    """Generate prompt guidance based on the quality assessment.

    Returns additional instructions to inject into the user prompt.
    """
    if report.level == "good":
        return ""

    parts: list[str] = []

    if report.level == "poor":
        parts.extend([
            "## 低质量字幕特别处理指令",
            "",
            "本次提供的字幕由自动语音识别生成，**质量较差**。请严格遵循以下额外规则：",
            "",
            "1. **宁可标注，不要硬猜**：任何语义不完整、术语听不清、前后矛盾的地方，"
            "必须标注 `[unclear]` 或 `[推测：xxx]`，绝对不要自行补全专业术语或公式。",
            "2. **跨段拼接语义**：ASR 按时间窗口切分，大量句子被截断。"
            "阅读时请跨越多段重新组织语义，不要逐段机械总结。",
            "3. **忽略噪音**：跳过明显的识别噪音、重复词、语气填充词、无意义音节。",
            "4. **降低图示要求**：本次不要输出结构化图示，文本质量不足以支撑准确的知识关系提取。",
            "5. **优先保证结构**：如果内容太碎无法填满五段，保持结构框架，"
            "在正文中用 `[该部分内容因字幕质量不足无法还原]` 标注缺失。",
            "6. **降低考试提示密度**：不要强行补全必考点/易错点提示，"
            "只在能确定教师确实提到时保留。",
        ])
    elif report.level == "medium":
        parts.extend([
            "## 中等质量字幕处理指令",
            "",
            "本次字幕可能由自动语音识别生成，存在部分质量问题。请注意：",
            "",
            "1. 不确定的内容标注 `[unclear]`。",
            "2. 注意跨段拼接被截断的句子。",
            "3. 忽略识别噪音和语气填充词。",
            "4. 结构化图示只在内容足够确定时才输出。",
        ])

    # Always include the markdown quality report
    report_md = report.markdown()
    if report_md:
        parts.append(report_md)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Domain classification
# ---------------------------------------------------------------------------


@dataclass
class DomainReport:
    """Domain classification result for a transcript."""
    domain: str = "stem"
    confidence: float = 0.0
    stem_score: float = 0.0
    social_science_score: float = 0.0
    source_signals: list[str] = field(default_factory=list)

    def summary(self) -> str:
        label = {"stem": "STEM/理工", "social_science": "社科/人文"}
        return (
            f"领域分类：{label.get(self.domain, self.domain)} "
            f"(置信度 {self.confidence:.0%})"
        )


def classify_domain(
    segments: list[dict],
    course_name: str = "",
    transcript_path: str = "",
) -> DomainReport:
    """Classify a transcript as STEM or social science.

    Detection signals (weighted):
    1. Course name keyword match (3x)
    2. Content keyword frequency from transcript sampling (1x)
    3. Filename keyword match (2x)
    """
    report = DomainReport()
    stem_hits: float = 0.0
    ss_hits: float = 0.0
    signals: list[str] = []

    # Signal 1: Course name keywords (weight 3x)
    if course_name:
        name_tokens = re.split(r"[\s\-_（）()【】\[\]：:，,]+", course_name)
        for token in name_tokens:
            if not token:
                continue
            for kw in STEM_KEYWORDS:
                if kw in token:
                    stem_hits += 3.0
                    signals.append(f"course_name_stem: {kw}")
            for kw in SOCIAL_SCIENCE_KEYWORDS:
                if kw in token:
                    ss_hits += 3.0
                    signals.append(f"course_name_ss: {kw}")

    # Signal 2: Content keyword sampling (weight 1x, sample up to 200 segments)
    if segments:
        sample_step = max(1, len(segments) // 200)
        sampled_text = " ".join(
            seg.get("text", "")
            for i, seg in enumerate(segments)
            if i % sample_step == 0
        )
        for kw in STEM_KEYWORDS:
            count = sampled_text.count(kw)
            if count:
                stem_hits += count
                if count >= 3:
                    signals.append(f"content_stem: {kw}:{count}")
        for kw in SOCIAL_SCIENCE_KEYWORDS:
            count = sampled_text.count(kw)
            if count:
                ss_hits += count
                if count >= 3:
                    signals.append(f"content_ss: {kw}:{count}")

    # Signal 3: Filename keywords (weight 2x)
    if transcript_path:
        fname_stem = os.path.splitext(os.path.basename(transcript_path))[0]
        for kw in STEM_KEYWORDS:
            if kw in fname_stem:
                stem_hits += 2.0
                signals.append(f"filename_stem: {kw}")
        for kw in SOCIAL_SCIENCE_KEYWORDS:
            if kw in fname_stem:
                ss_hits += 2.0
                signals.append(f"filename_ss: {kw}")

    report.stem_score = stem_hits
    report.social_science_score = ss_hits

    if stem_hits == 0 and ss_hits == 0:
        report.domain = "stem"
        report.confidence = 0.0
        report.source_signals = ["no_signal_found"]
        return report

    total = stem_hits + ss_hits
    report.confidence = abs(stem_hits - ss_hits) / total

    if stem_hits >= ss_hits:
        report.domain = "stem"
    else:
        report.domain = "social_science"

    report.source_signals = signals[:8]
    return report


def domain_guidance(report: DomainReport) -> str:
    """Generate domain-specific prompt guidance.

    Returns "" for STEM (system.md is already STEM-optimized).
    Returns social-science adaptations when detected as social science.
    """
    if report.domain != "social_science" or report.confidence < 0.3:
        return ""

    parts: list[str] = [
        "## 社科类课程特别指引",
        "",
        "本次课程识别为**社会科学/人文类**。请在生成笔记时应用以下调整：",
        "",
        "### 二、正文内容要素调整",
        "- 将\"定义/概念 → 公式/定律 → 推导过程 → 物理意义\"替换为：**理论框架 → 论点/论据 → 案例分析 → 学派对比**",
        "- 不要强行寻找或编造\"公式\"；社科课程的核心是理论主张、论证逻辑和案例支撑",
        "- 注意提取教师讲解中的**论述题答题框架**（总论点 → 分论点 → 论据要点）",
        "",
        "### 四、作业与考试重点调整",
        "- **将\"必考公式汇总\"表格替换为\"核心理论/学者观点\"表格**：",
        "  | 理论/观点 | 提出者/学派 | 核心内容 | 适用分析场景 |",
        "- **增加论述题答题框架**：若教师提及可能的论述题方向，列出总分总结构要点",
        "- **必记概念清单**使用名词解释风格：每条附简短解释（考试中可能作为名词解释题出现）",
        "",
        "### 结构化图示调整",
        "- 优先使用 `comparison`（学派对比、制度对比、概念辨析）和 `flow`（逻辑推演、历史进程）",
        "- 不使用 `formula_map`",
        "- 若内容适合展示概念关系，使用 `comparison` 类型的双栏对比",
    ]
    return "\n\n".join(parts)


def _parse_srt_timestamp(value: str) -> float:
    hours, minutes, seconds = re.split(r":", value.replace(",", "."))
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def read_file(filepath: str) -> str:
    """Read any supported file (.srt / .txt / .md) and return its text content."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except OSError as e:
        raise ValueError(f"读取文件失败：{e}") from e

    content = raw.strip()
    if not content:
        raise ValueError("输入文件内容为空")
    return content


def parse_srt_text(filepath: str) -> str:
    """Parse .srt file and return a continuous transcript.

    For .srt files, extracts only the spoken text with timestamps.
    For .txt/.md files, returns the raw content.
    """
    if not filepath.lower().endswith(".srt"):
        return read_file(filepath)

    segments = parse_srt_segments(filepath)
    if not segments:
        return read_file(filepath)

    lines: list[str] = []
    for seg in segments:
        start = format_seconds(seg["start_seconds"])
        end = format_seconds(seg["end_seconds"])
        text = seg["text"]
        lines.append(f"[{start} → {end}] {text}")

    return "\n".join(lines)


def parse_srt_segments(filepath: str) -> list[dict]:
    """Parse .srt file into structured segments.

    Each segment: {start_seconds, end_seconds, text}.
    Non-.srt files return an empty list.
    """
    if not filepath.lower().endswith(".srt"):
        return []

    content = read_file(filepath)
    blocks = re.split(r"\n\s*\n", content)
    segments: list[dict] = []

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        time_line = next((line for line in lines if "-->" in line), "")
        match = SRT_TIME_RE.search(time_line)
        if not match:
            continue
        text_lines = [
            line for line in lines if line != time_line and not line.isdigit()
        ]
        text = " ".join(text_lines).strip()
        if not text:
            continue
        start_seconds = _parse_srt_timestamp(match.group("start"))
        end_seconds = _parse_srt_timestamp(match.group("end"))
        if end_seconds <= start_seconds:
            continue
        segments.append(
            {
                "start_seconds": start_seconds,
                "end_seconds": end_seconds,
                "text": text,
            }
        )
    return segments




