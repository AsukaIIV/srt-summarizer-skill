#!/usr/bin/env python3
"""Batch generate ultra-detailed notes via proxy API (v4-pro).

Reads SRT files grouped by chapter, calls v4-pro API with retry,
merges per-chapter results into chapter-level notes.

Usage:
    python3 scripts/generate_gaoshu.py --srt-dir <path> --out-dir <path> --course <name> [--api-url <url>]

Configurable via CLI args. Defaults to 高数 but works for any course.
"""

import os, re, sys, json, time, glob, argparse
import urllib.request, urllib.error

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Defaults ──────────────────────────────────────────────
DEFAULT_SRT_DIR = "/vol2/1000/hdd0/重要文件/obsidian_library/课程录音/高数/高数课程录音"
DEFAULT_OUT_DIR = "/vol2/1000/hdd0/重要文件/obsidian_library/课程录音/高数/超详细笔记"
DEFAULT_COURSE  = "高等数学"

# Load API config from .env
def load_env():
    env_file = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                k, _, v = line.partition("=")
                os.environ[k.strip()] = v.strip()

load_env()

# ── System prompt (精简版 ~2.5KB) ────────────────────────
SYSTEM_PROMPT = """你是一位专业的课堂笔记生成专家，将字幕转录文本整理为超详细Markdown课堂笔记。

## 格式要求
1. **五段结构**：## 一、课程概要 → ## 二、正文内容 → ## 三、教师强调重点 → ## 四、作业与考试重点 → ## 五、课程总结
2. **超详细展开**：每知识点 定义→公式→推导过程→典型例题→注意事项 六要素
3. **知识地图**：正文开头用 $$\\\\begin{array}{c}...\\\\end{array}$$ 绘制知识流向图，\\\\downarrow 表示流向
4. **题型总览表 + 易错点汇总 + 常用结论速查**：正文末尾（三之前）必须包含
5. **例题**：每章≥8道，step-by-step完整求解
6. **公式**：全部LaTeX，行内$...$ 块级$$...$$，Unicode数学字符转LaTeX命令
7. **禁止**：#一级标题（只能用##/###/####）、开场白废话、臆造内容、backtick代码写公式
8. **结构化图示**：文末用 ## 结构化图示输出 区块 + ```json {\\"diagrams\\":[...]}

## 严格约束
- 输出必须以 ## 一、课程概要 开头，此前无任何文字
- 不确定内容标注 [unclear]，绝对不猜测
- 每节末尾输出知识地图：$$\\\\begin{array}{c}...\\\\end{array}$$
- 公式中 Unicode λ μ θ ω η ≈ · ½ √ ₁₂₃ ⁰¹²³ 必须转 LaTeX"""

def parse_args():
    parser = argparse.ArgumentParser(description="Batch generate ultra-detailed notes")
    parser.add_argument("--srt-dir", default=DEFAULT_SRT_DIR, help="SRT files directory")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="Output directory for notes")
    parser.add_argument("--course", default=DEFAULT_COURSE, help="Course name")
    parser.add_argument("--api-url", default="http://47.251.108.225:3000/v1/chat/completions",
                        help="API endpoint URL")
    parser.add_argument("--model", default="deepseek-ai/deepseek-v4-pro",
                        help="Model name")
    parser.add_argument("--chunk-size", type=int, default=20000,
                        help="Max bytes per chunk (default: 20000)")
    parser.add_argument("--retries", type=int, default=6,
                        help="Max retries per API call (default: 6)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only show group breakdown, don't call API")
    return parser.parse_args()


def group_srt_by_chapter(srt_dir: str) -> dict[str, list[str]]:
    """Group SRT files by chapter number from filename."""
    srt_files = sorted([
        os.path.join(srt_dir, f) for f in os.listdir(srt_dir)
        if f.endswith(".srt")
    ])
    chapters: dict[str, list[str]] = {}
    for fp in srt_files:
        fn = os.path.basename(fp)
        m = re.search(r'【第(\d+)章】', fn)
        if m:
            ch = f"第{m.group(1)}章"
        else:
            # Fallback: group by first YYYYMMDD or prefix
            m2 = re.match(r"(\d{4}\d{2}\d{2})", fn)
            if m2:
                ch = f"日期_{m2.group(1)}"
            else:
                ch = "其他"
        chapters.setdefault(ch, []).append(fp)
    return dict(sorted(chapters.items(), key=lambda x: (
        0 if x[0].startswith("第") else 1,
        int(re.search(r"\d+", x[0]).group()) if re.search(r"\d+", x[0]) else 0,
    )))


def merge_chapter_text(chapter_files: list[str], max_bytes: int = 20000) -> list[str]:
    """Merge SRT files into a single text, then split into chunks of max_bytes."""
    all_lines: list[str] = []
    for fp in chapter_files:
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            lines = content.split("\n")
            text_lines = [
                line for line in lines
                if line.strip()
                and not re.match(r"^\d+$", line)
                and not re.match(r"^\d{2}:\d{2}:\d{2}", line)
            ]
            all_lines.extend(text_lines)
        except Exception as e:
            print(f"  ⚠ 读取失败 {os.path.basename(fp)}: {e}")

    full_text = "\n".join(all_lines)

    # Split into chunks
    chunks: list[str] = []
    current: list[str] = []
    current_bytes = 0
    for line in full_text.split("\n"):
        line_bytes = len(line.encode("utf-8")) + 1
        if current_bytes + line_bytes > max_bytes and current:
            chunks.append("\n".join(current))
            current = [line]
            current_bytes = line_bytes
        else:
            current.append(line)
            current_bytes += line_bytes
    if current:
        chunks.append("\n".join(current))
    return chunks


def call_api(user_text: str, api_url: str, model: str, api_key: str,
             max_retries: int = 6, timeout: int = 900) -> str | None:
    """Call the proxy API with exponential backoff retry."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"请生成超详细笔记。\n\n{user_text}"}
        ],
        "max_tokens": 16384,
        "temperature": 0.3,
    }
    data = json.dumps(payload).encode("utf-8")

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                api_url, data=data,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read())
                return result["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code == 504 and attempt < max_retries - 1:
                wait = min(30 * (2 ** attempt), 600)
                print(f"    504 超时，{wait}s后重试 ({attempt + 2}/{max_retries})...")
                time.sleep(wait)
                continue
            print(f"    HTTP {e.code}: {e.reason}")
            if attempt < max_retries - 1:
                time.sleep(30)
                continue
            return None
        except Exception as e:
            err_msg = str(e)
            if "Broken pipe" in err_msg or "Connection reset" in err_msg:
                wait = min(30 * (2 ** attempt), 600)
                print(f"    连接断开，{wait}s后重试 ({attempt + 2}/{max_retries})...")
                time.sleep(wait)
                continue
            print(f"    异常: {err_msg}")
            if attempt < max_retries - 1:
                time.sleep(30)
                continue
            return None
    return None


def save_with_cache(chapter_label: str, group_idx: int, text: str,
                    result: str, cache_dir: str) -> bool:
    """Save result to cache. Returns True if successful."""
    cache_file = os.path.join(cache_dir, f"{chapter_label}_g{group_idx:02d}.md")
    with open(cache_file, "w", encoding="utf-8") as f:
        f.write("OK:" + result)
    return True


def load_cache(chapter_label: str, group_idx: int, cache_dir: str) -> str | None:
    """Load cached result if exists. Returns content or None."""
    cache_file = os.path.join(cache_dir, f"{chapter_label}_g{group_idx:02d}.md")
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            cached = f.read()
        if cached.startswith("OK:"):
            return cached[3:]
    return None


def clear_cache(chapter_label: str, cache_dir: str):
    """Clear cache files for a chapter after successful merge."""
    for cf in glob.glob(os.path.join(cache_dir, f"{chapter_label}_*.md")):
        os.remove(cf)


def main():
    args = parse_args()

    print(f"=== 批量笔记生成 ===")
    print(f"课程: {args.course}")
    print(f"SRT目录: {args.srt_dir}")
    print(f"输出目录: {args.out_dir}")
    print(f"API: {args.api_url}")
    print(f"Model: {args.model}")
    print()

    if not os.path.isdir(args.srt_dir):
        print(f"✗ SRT目录不存在: {args.srt_dir}")
        sys.exit(1)

    os.makedirs(args.out_dir, exist_ok=True)
    cache_dir = os.path.join(args.out_dir, "_cache")
    os.makedirs(cache_dir, exist_ok=True)

    # Get API key
    api_key = os.environ.get("QWEN_VISION_API_KEY", "")
    if not api_key:
        # Try hermes config
        try:
            import subprocess
            r = subprocess.run(["hermes", "config", "get", "providers.custom.api_key"],
                             capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                api_key = r.stdout.strip()
        except Exception:
            pass

    if not api_key:
        print("✗ 未找到 API Key。确保 ~/.hermes/.env 中有 QWEN_VISION_API_KEY")
        sys.exit(1)

    # Group SRTs by chapter
    chapters = group_srt_by_chapter(args.srt_dir)
    print(f"发现 {len(chapters)} 章:")
    for ch in chapters:
        print(f"  {ch}: {len(chapters[ch])} 个SRT文件")
    print()

    if args.dry_run:
        print("Dry-run 模式，退出")
        return

    # Process each chapter
    total_chapters = len(chapters)
    for ch_idx, (chapter_label, srt_files) in enumerate(chapters.items(), 1):
        print(f"\n── [{ch_idx}/{total_chapters}] {chapter_label} ──")

        # Merge and split
        chunks = merge_chapter_text(srt_files, max_bytes=args.chunk_size)
        print(f"  合并后拆分: {len(chunks)} 组")

        if not chunks:
            print(f"  ⚠ 无有效内容，跳过")
            continue

        # Check cache
        results: list[str] = []
        all_cached = True
        for i in range(len(chunks)):
            cached = load_cache(chapter_label, i + 1, cache_dir)
            if cached:
                results.append(cached)
            else:
                all_cached = False
                results.append(None)  # placeholder

        if all_cached:
            print(f"  全部从缓存加载 ✓")
        else:
            # Generate uncached chunks
            for i, (chunk, cached_result) in enumerate(zip(chunks, results)):
                if cached_result is not None:
                    print(f"  组{i+1}: 缓存 ✓")
                    continue

                chunk_size_kb = len(chunk.encode("utf-8")) / 1024
                print(f"  组{i+1}: {chunk_size_kb:.0f}KB → API调用...")

                result = call_api(
                    chunk, args.api_url, args.model, api_key,
                    max_retries=args.retries,
                )

                if result:
                    save_with_cache(chapter_label, i + 1, chunk, result, cache_dir)
                    results[i] = result
                    print(f"    完成 ({len(result)} 字符)")
                else:
                    results[i] = f"\n[组{i+1} 生成失败]\n"
                    print(f"    ✗ 失败")
                time.sleep(2)  # group pause

        # Merge results → chapter note
        chapter_header = f"# 📐 {chapter_label}（超详细版）\n\n> 课程：{args.course}\n> 笔记按超详细模板生成\n>\n---\n\n"
        merged = chapter_header + "\n\n---\n\n".join(
            r for r in results if r  # skip None/failed
        )
        out_path = os.path.join(args.out_dir, f"{chapter_label}_超详细笔记.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(merged)
        print(f"  ✅ {chapter_label}: {os.path.basename(out_path)} ({len(merged)} 字符)")

        # Clear cache for this chapter
        clear_cache(chapter_label, cache_dir)

    print(f"\n✅ 完成! 笔记保存在: {args.out_dir}")


if __name__ == "__main__":
    main()
