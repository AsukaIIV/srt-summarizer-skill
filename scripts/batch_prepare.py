"""Batch preparation: scan, parse, assess quality, classify domain, extract frames.
Outputs a JSON report with full context for note generation.

Usage:
    # Default (通信电子线路)
    python3 scripts/batch_prepare.py

    # Custom course
    python3 scripts/batch_prepare.py --course 光纤通信 \
        --offline-dir /path/to/srt/dir \
        --out-dir /path/to/output
"""

import json, os, re, sys, traceback, argparse
from datetime import datetime

# Add skill root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.scanner import scan_and_pair
from scripts.parse_srt import (
    parse_srt_text, parse_srt_segments,
    assess_quality, quality_guidance,
    classify_domain, domain_guidance,
)
from scripts.video_frames import extract_frames

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Default paths (通信电子线路) ──────────────────────────
DEFAULT_OFFLINE_DIR = "/vol2/1000/hdd0/重要文件/obsidian_library/课程录音/通信电子线路/课程录音字幕"
DEFAULT_ONLINE_DIR  = "/vol2/1000/hdd0/重要文件/obsidian_library/课程录音/通信电子线路/通信电子线路课件/网络课程"
DEFAULT_OUTPUT_BASE = "/vol2/1000/hdd0/重要文件/obsidian_library/课程录音/通信电子线路"
DEFAULT_COURSE_NAME = "通信电子线路"

# ── Week mapping (extendable) ────────────────────────────
DEFAULT_WEEK_MAP = {
    "20260317": ("第1周", "2026-03-17"),
    "20260319": ("第2周", "2026-03-19"),
    "20260324": ("第3周", "2026-03-24"),
    "20260331": ("第4周", "2026-03-31"),
    "20260402": ("第5周", "2026-04-02"),
    "20260407": ("第6周", "2026-04-07"),
    "20260409": ("第7周", "2026-04-09"),
    "20260414": ("第8周", "2026-04-14"),
    "20260416": ("第9周", "2026-04-16"),
    "20260421": ("第10周", "2026-04-21"),
    "20260428": ("第11周", "2026-04-28"),
    "20260430": ("第12周", "2026-04-30"),
    "20260512": ("第13周", "2026-05-12"),
    "20260514": ("第14周", "2026-05-14"),
    "20260519": ("第15周", "2026-05-19"),
}


def get_source_type(lesson, offline_dir, online_dir):
    """Determine if offline (线下课) or online (网络课)."""
    p = lesson["transcript_path"]
    if offline_dir in p:
        return "线下课"
    elif online_dir in p:
        return "网络课"
    return "未知"


def get_lesson_title(lesson, idx, course_name, week_map):
    """Generate lesson title: YYYY-MM-DD_{第X周}_{topic}"""
    from scripts._utils import sanitize_filename
    stem = os.path.splitext(os.path.basename(lesson["transcript_path"]))[0]

    # Extract YYYYMMDD from filename
    m = re.search(r"(\d{4})(\d{2})(\d{2})", stem)
    if m:
        yyyymmdd = m.group(1) + m.group(2) + m.group(3)
        date_str = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        week_info = week_map.get(yyyymmdd, ("", date_str))
        week_str = week_info[0]
        date_str = week_info[1]
    else:
        date_str = "未知日期"
        week_str = ""

    # Clean up topic from stem
    topic = stem
    topic = re.sub(r"^\d{8}_\d{6}\.?", "", topic)
    topic = re.sub(r"^\d{8}\.?", "", topic)
    topic = re.sub(r"\.zh\.whisperjav$", "", topic)
    topic = topic.strip("._- ")

    if not topic:
        topic = f"{course_name}{idx+1}"

    title = f"{date_str}_{week_str}_{topic}" if week_str else f"{date_str}_{topic}"
    return sanitize_filename(title, fallback=f"{course_name}_{idx+1}")


def process_lesson(lesson, idx, total, course_name, output_base, week_map, offline_dir, online_dir):
    """Process a single lesson: parse, assess, classify."""
    source_type = get_source_type(lesson, offline_dir, online_dir)
    print(f"\n{'='*60}")
    print(f"处理第 {idx+1}/{total} 节课 [{source_type}]")
    print(f"SRT: {os.path.basename(lesson['transcript_path'])}")

    result = {
        "index": idx + 1,
        "source_type": source_type,
        "transcript_path": lesson["transcript_path"],
        "transcript_name": os.path.basename(lesson["transcript_path"]),
        "video_path": lesson.get("video_path", ""),
        "status": "pending",
        "errors": [],
    }

    # Step 1: Parse SRT
    try:
        segments = parse_srt_segments(lesson["transcript_path"])
        transcript_text = parse_srt_text(lesson["transcript_path"])
        result["segments_count"] = len(segments)
        result["transcript_length"] = len(transcript_text)
        print(f"  解析：{len(segments)} 段字幕，共 {len(transcript_text)} 字符")
    except Exception as e:
        result["status"] = "parse_failed"
        result["errors"].append(f"解析失败：{e}")
        print(f"  ✗ 解析失败：{e}")
        return result

    # Step 2: Quality assessment
    try:
        quality_report = assess_quality(segments)
        quality_guide = quality_guidance(quality_report)
        result["quality_score"] = quality_report.overall_score
        result["quality_level"] = quality_report.level
        result["quality_summary"] = quality_report.summary()
        result["quality_guidance"] = quality_guide
        print(f"  质量：{quality_report.summary()}")
    except Exception as e:
        result["quality_score"] = 100
        result["quality_level"] = "unknown"
        result["quality_summary"] = f"评估失败：{e}"
        result["quality_guidance"] = ""
        print(f"  ⚠ 质量评估异常：{e}")

    # Step 3: Domain classification
    try:
        domain_report = classify_domain(
            segments,
            course_name=course_name,
            transcript_path=lesson["transcript_path"],
        )
        domain_guide = domain_guidance(domain_report)
        result["domain"] = domain_report.domain
        result["domain_summary"] = domain_report.summary()
        result["domain_guidance"] = domain_guide
        print(f"  领域：{domain_report.summary()}")
    except Exception as e:
        result["domain"] = "stem"
        result["domain_summary"] = f"分类失败：{e}"
        result["domain_guidance"] = ""
        print(f"  ⚠ 领域分类异常：{e}")

    # Step 4: Extract video frames (only for network courses with video)
    frame_entries = []
    if source_type == "网络课" and lesson.get("video_path"):
        video_path = lesson["video_path"]
        if os.path.isfile(video_path):
            try:
                lesson_title = get_lesson_title(lesson, idx,
                                                 course_name, week_map)
                from scripts.writer import build_output_paths
                _, img_dir, _ = build_output_paths(
                    source_file=lesson["transcript_path"],
                    save_dir=output_base,
                    course_name=course_name,
                    lesson_title=lesson_title,
                )

                print(f"  提取视频帧：{os.path.basename(video_path)}")
                saved_paths, frame_items = extract_frames(
                    video_path=video_path,
                    image_dir=img_dir,
                    max_frames=6,
                    subtitle_segments=segments,
                    course_name=course_name,
                )
                result["frame_count"] = len(saved_paths)
                result["frame_entries"] = frame_items
                result["img_dir"] = img_dir
                print(f"  截图：{len(saved_paths)} 帧 → {img_dir}")
            except Exception as e:
                result["frame_count"] = 0
                result["frame_entries"] = []
                result["img_dir"] = ""
                result["errors"].append(f"截图提取异常：{e}")
                print(f"  ⚠ 截图提取异常：{e}")
        else:
            result["frame_count"] = 0
            result["frame_entries"] = []
            print(f"  视频文件不存在：{video_path}")
    else:
        result["frame_count"] = 0
        result["frame_entries"] = []
        if source_type == "线下课":
            print(f"  线下课：无需截图")

    # Step 5: Generate lesson title info
    result["lesson_title"] = get_lesson_title(lesson, idx,
                                               course_name, week_map)

    result["status"] = "ready"
    return result


def parse_args():
    parser = argparse.ArgumentParser(description="Batch prepare SRT files for note generation")
    parser.add_argument("--course", default=DEFAULT_COURSE_NAME, help="Course name")
    parser.add_argument("--offline-dir", default=DEFAULT_OFFLINE_DIR, help="Offline SRT directory")
    parser.add_argument("--online-dir", default=DEFAULT_ONLINE_DIR, help="Online course SRT directory")
    parser.add_argument("--out-dir", default=DEFAULT_OUTPUT_BASE, help="Output base directory")
    parser.add_argument("--report-path", default="", help="Report JSON path (default: skill dir)")
    parser.add_argument("--week-map", default="", help="JSON file with week mappings (optional)")
    return parser.parse_args()


def main():
    args = parse_args()

    course_name = args.course
    offline_dir = args.offline_dir
    online_dir = args.online_dir
    output_base = args.out_dir

    # Load week map (default or from file)
    week_map = dict(DEFAULT_WEEK_MAP)
    if args.week_map and os.path.isfile(args.week_map):
        with open(args.week_map, "r", encoding="utf-8") as f:
            user_map = json.load(f)
            week_map.update(user_map)

    report_path = args.report_path or os.path.join(SKILL_DIR, f"batch_report_{course_name}.json")

    print(f"=== SRT-SUMMARIZER 批量准备 ===")
    print(f"课程名称：{course_name}")
    print(f"输出目录：{output_base}")
    print(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Scan directories
    lessons_all = []

    if os.path.isdir(offline_dir):
        print("扫描线下课目录...")
        offline_result = scan_and_pair(offline_dir)
        print(f"  发现 {len(offline_result['lessons'])} 节线下课")
        lessons_all.extend(offline_result["lessons"])
    else:
        print(f"  线下课目录不存在: {offline_dir}，跳过")

    if os.path.isdir(online_dir):
        print("扫描网络课目录...")
        online_result = scan_and_pair(online_dir)
        print(f"  发现 {len(online_result['lessons'])} 节网络课")
        lessons_all.extend(online_result["lessons"])
    else:
        print(f"  网络课目录不存在: {online_dir}，跳过")

    total = len(lessons_all)
    print(f"\n共 {total} 节课")

    # Process each lesson
    results = []
    for idx, lesson in enumerate(lessons_all):
        r = process_lesson(lesson, idx, total, course_name, output_base,
                           week_map, offline_dir, online_dir)
        results.append(r)

    # Summary
    ready = [r for r in results if r["status"] == "ready"]
    failed = [r for r in results if r["status"] != "ready"]
    print(f"\n{'='*60}")
    print(f"准备完成：{len(ready)} 节就绪，{len(failed)} 节失败")

    for r in ready:
        frames = r.get("frame_count", 0)
        frame_str = f" | 截图 {frames} 帧" if frames else ""
        print(f"  ✓ [{r['source_type']}] #{r['index']} {r['lesson_title']} "
              f"| 质量 {r['quality_score']}/100 ({r['quality_level']})"
              f" | {r.get('domain', 'stem')}"
              f"{frame_str}")

    for r in failed:
        print(f"  ✗ #{r['index']} {r.get('transcript_name','')}: {r.get('errors',['未知'])}")

    # Write report
    report = {
        "course_name": course_name,
        "output_base": output_base,
        "generated_at": datetime.now().isoformat(),
        "total": total,
        "ready": len(ready),
        "failed": len(failed),
        "lessons": results,
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告已保存：{report_path}")

    print(f"\n{'='*60}")
    print("下一步：逐节使用 delegate_task 生成笔记")


if __name__ == "__main__":
    main()
