"""通用后处理: 修复笔记中的 JSON 结构化图示 → LaTeX array 知识地图。

将 system.md 生成的 JSON 结构化图示替换为用户偏好的 LaTeX array 紧凑格式。
同时修复截图路径（绝对路径→相对路径），确保 JSON 区块在文件末尾。

Usage:
    python3 scripts/render_all.py [--course 课程名] [--dir /path/to/notes]

Options:
    --course     课程文件夹名（默认：通信电子线路）
    --dir        直接指定笔记目录（优先级高于--course）
    --fix-only   只修复路径/位置，不渲染图示
"""

import os, re, glob, json, sys, argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Default base directory
DEFAULT_BASE = "/vol2/1000/hdd0/重要文件/obsidian_library/课程录音/通信电子线路"


def parse_args():
    parser = argparse.ArgumentParser(description="Post-process notes: fix JSON/json → LaTeX, paths")
    parser.add_argument("--course", default="", help="Course folder name under 课程录音/")
    parser.add_argument("--dir", default="", help="Direct path to notes directory")
    parser.add_argument("--fix-only", action="store_true", help="Only fix paths/position, no rendering")
    return parser.parse_args()


def json_to_latex_array(json_spec: dict) -> str:
    """Convert a JSON diagram spec to a LaTeX array knowledge map."""
    if not json_spec or "diagrams" not in json_spec:
        return ""

    diagrams = json_spec["diagrams"]
    if not diagrams:
        return ""

    parts = []
    for d in diagrams:
        t = d.get("type", "flow")
        title = d.get("title", "")
        lines = [rf"\textbf{{{title}}}" if title else ""]

        if t == "comparison":
            left = d.get("left_title", "左")
            right = d.get("right_title", "右")
            left_items = d.get("left_items", [])
            right_items = d.get("right_items", [])
            max_items = max(len(left_items), len(right_items))
            for i in range(max_items):
                li = left_items[i] if i < len(left_items) else ""
                ri = right_items[i] if i < len(right_items) else ""
                lines.append(rf"\text{{{li}}} \quad\longleftrightarrow\quad \text{{{ri}}}")

        elif t == "flow":
            steps = d.get("steps", [])
            for i, step in enumerate(steps):
                arrow = r"\downarrow" if i < len(steps) - 1 else ""
                lines.append(rf"\text{{{step}}} \\ {arrow}")

        elif t == "formula_map":
            central = d.get("central_formula", "")
            branches = d.get("branches", [])
            lines.append(rf"\text{{{central}}}")
            for i, branch in enumerate(branches):
                if i == 0:
                    lines.append(r"\swarrow \searrow")
                lines.append(rf"\text{{{branch}}}")
                if i < len(branches) - 1:
                    lines.append(r"\swarrow \searrow")

        array_content = r" \\\\ ".join(line for line in lines if line)
        parts.append(rf"$$\begin{{array}}{{c}}{array_content}\end{{array}}$$")

    return "\n\n".join(parts)


def fix_markdown(content: str) -> tuple[str, bool, str]:
    """Fix a note's markdown content. Returns (fixed_content, was_modified, notes)."""
    orig = content
    notes = ""

    # Strip YAML frontmatter
    frontmatter = ""
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[0] + "---" + parts[1] + "---\n\n"
            body = parts[2]

    # Fix 1: Replace absolute paths
    body = re.sub(r"/vol[123]/1000/[^/]+/\S*?/imgs/", "imgs/", body)
    body = re.sub(r"未知日期_[^/]+/imgs/", "imgs/", body)

    # Fix 2: Find JSON structured diagram section and convert to LaTeX array
    json_section = re.search(
        r"##\s+结构化图示输出\s*\n+```json\s*\n([\s\S]*?)```",
        body
    )

    if json_section:
        try:
            json_text = json_section.group(1).strip()
            spec = json.loads(json_text)
            latex_array = json_to_latex_array(spec)
            if latex_array:
                # Replace JSON block with LaTeX array
                body = body[:json_section.start()] + "## 结构化图示输出\n\n" + latex_array + "\n"
                notes += "JSON→LaTeX array ✓ "
        except (json.JSONDecodeError, Exception):
            notes += "JSON解析失败，保留原样 ⚠ "

    # Fix 3: Ensure ## 结构化图示输出 is at end
    diagram_section = re.search(
        r"\n##\s+结构化图示输出\s*\n[\s\S]*$",
        body
    )
    if diagram_section:
        # Move to end (if not already)
        section = diagram_section.group(0)
        before = body[:diagram_section.start()].strip()
        body = before + "\n\n" + section + "\n"

    # Fix 4: Close unclosed json code blocks
    body = re.sub(r"```json\s*$", "```json\n```\n", body)  # if json at very end without closing

    modified = body != (content[len(frontmatter):] if frontmatter else content)
    if modified:
        content = frontmatter + body

    return content, modified, notes


def main():
    args = parse_args()

    if args.dir:
        base = args.dir
    elif args.course:
        base = f"/vol2/1000/hdd0/重要文件/obsidian_library/课程录音/{args.course}"
    else:
        base = DEFAULT_BASE

    if not os.path.isdir(base):
        print(f"✗ 目录不存在: {base}")
        sys.exit(1)

    print(f"处理目录: {base}\n")
    fixed_count = 0
    total = 0

    for nd in sorted(os.listdir(base)):
        nd_path = os.path.join(base, nd)
        if not os.path.isdir(nd_path):
            continue
        if nd in ("课程录音字幕", "通信电子线路课件") or nd.startswith("未知日期_"):
            continue
        mds = glob.glob(os.path.join(nd_path, "*.md"))
        if not mds:
            continue

        total += 1
        md = mds[0]
        try:
            with open(md, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"  ⚠ {nd}: 读取失败 - {e}")
            continue

        fixed_content, modified, notes = fix_markdown(content)
        if modified:
            with open(md, "w", encoding="utf-8") as f:
                f.write(fixed_content)
            fixed_count += 1
            status = notes if notes else "格式修复"
            print(f"  ✅ {nd}: {status}")
        else:
            print(f"  ·  {nd}: 无需修复")

    print(f"\n扫描 {total} 篇，修复 {fixed_count} 篇")


if __name__ == "__main__":
    main()
