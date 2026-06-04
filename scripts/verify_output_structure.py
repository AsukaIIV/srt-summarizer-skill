"""Verify subagent output structure and naming conventions.

Checks:
  1. Folder name matches YYYY-MM-DD_第X周_主题
  2. .md file name matches folder name
  3. imgs/ subdirectory exists

Usage:
  python3 scripts/verify_output_structure.py /path/to/output/课程名/
"""

import os
import re
import sys

# "YYYY-MM-DD_第?周_description"
FOLDER_PATTERN = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})_第(\d+)周_(.+)$"
)

# Relaxed: matches any folder that starts with YYYY-MM-DD_
LOOSE_PATTERN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})_.+$")


def verify_output_structure(base_dir: str) -> tuple[list[str], list[str], list[str]]:
    """Scan base_dir and return (ok, warn, err) lists.

    Each entry is a human-readable status line.
    """
    ok: list[str] = []
    warn: list[str] = []
    err: list[str] = []

    if not os.path.isdir(base_dir):
        err.append(f"目录不存在: {base_dir}")
        return ok, warn, err

    entries = [
        e for e in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, e))
    ]

    if not entries:
        warn.append("未发现任何子目录，请确认子代理是否正确生成笔记")
        return ok, warn, err

    for entry in sorted(entries):
        entry_path = os.path.join(base_dir, entry)

        # ── 1. Check folder naming ──────────────────────────────
        match = FOLDER_PATTERN.match(entry)
        if match:
            year, month, day, week, topic = match.groups()
            ok.append(f"[格式正确] {entry}")
        elif LOOSE_PATTERN.match(entry):
            warn.append(
                f"[格式偏异] {entry} — 以日期开头但不符合 "
                f"`YYYY-MM-DD_第X周_主题` 规范"
            )
        else:
            err.append(
                f"[命名违规] {entry} — 目录名必须以 `YYYY-MM-DD_第X周_主题` 格式命名"
            )
            # Continue checking children even for badly-named folders
            # but don't require .md to match folder name
            _check_children(entry_path, entry, ok, warn, err, strict_name=False)
            continue

        # ── 2. Check .md file name matches folder name ──────────
        _check_children(entry_path, entry, ok, warn, err, strict_name=True)

    return ok, warn, err


def _check_children(
    entry_path: str,
    entry_name: str,
    ok: list[str],
    warn: list[str],
    err: list[str],
    strict_name: bool,
) -> None:
    """Check .md file naming and imgs/ subdirectory for a single entry."""
    md_files = [
        f for f in os.listdir(entry_path)
        if f.endswith(".md") and os.path.isfile(os.path.join(entry_path, f))
    ]
    imgs_dir = os.path.join(entry_path, "imgs")

    # Check .md file
    if not md_files:
        err.append(f"  └─ 缺少 .md 笔记文件: {entry_name}/")
    elif strict_name:
        expected_md = f"{entry_name}.md"
        if expected_md in md_files:
            ok.append(f"  └─ {expected_md} ✅")
        else:
            actual = md_files[0]
            warn.append(
                f"  └─ .md 文件名不匹配 — 期望 `{expected_md}`，实际 `{actual}`"
            )
        # Check for extra .md files
        if len(md_files) > 1:
            extras = [f for f in md_files if f != expected_md]
            warn.append(f"  └─ 多余 .md 文件: {', '.join(extras)}")
    else:
        ok.append(f"  └─ {md_files[0]} (命名未强制校验，父目录格式已违规)")

    # Check imgs/ subdirectory
    if os.path.isdir(imgs_dir):
        png_count = len([
            f for f in os.listdir(imgs_dir)
            if f.endswith(".png") and os.path.isfile(os.path.join(imgs_dir, f))
        ])
        if png_count > 0:
            ok.append(f"  └─ imgs/ (含 {png_count} 张 PNG) ✅")
        else:
            warn.append(f"  └─ imgs/ 存在但无 PNG 图片")
    else:
        warn.append(f"  └─ 缺少 imgs/ 子目录")


def main():
    if len(sys.argv) < 2:
        print("用法: python3 scripts/verify_output_structure.py <输出目录>")
        sys.exit(1)

    base_dir = sys.argv[1]
    ok, warn, err = verify_output_structure(base_dir)

    # ── Report ──────────────────────────────────────────────────
    print("=" * 72)
    print("输出结构验证报告")
    print("=" * 72)
    print(f"扫描目录: {base_dir}")
    print(f"子目录数: {len([e for e in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, e))])}")
    print()

    total_issues = len(warn) + len(err)

    if ok:
        for line in ok:
            print(f"  {line}")

    if warn:
        print(f"\n⚠ 警告 ({len(warn)}):")
        for line in warn:
            print(f"  {line}")

    if err:
        print(f"\n❌ 错误 ({len(err)}):")
        for line in err:
            print(f"  {line}")

    print()
    print("=" * 72)
    if err:
        print("❌ 验证失败：存在命名违规或缺失文件，请修正后重新生成。")
        sys.exit(1)
    elif warn:
        print("⚠ 验证通过但有警告，建议检查上述项。")
    else:
        print("✅ 全部验证通过！目录结构与命名均符合规范。")
    print("=" * 72)

    return total_issues


if __name__ == "__main__":
    main()
