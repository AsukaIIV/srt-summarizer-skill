"""Final verification."""
import os, glob, re

BASE = "/vol2/1000/hdd0/重要文件/obsidian_library/课程录音/通信电子线路"
note_dirs = sorted([d for d in os.listdir(BASE) if d not in ("课程录音字幕","通信电子线路课件") and not d.startswith("未知日期_") and os.path.isdir(os.path.join(BASE, d))])

total_notes = 0
total_screenshots = 0
total_diagrams = 0
issues = []

print("=" * 100)
print(f"{'笔记目录':55s} | {'MD':4s} | {'截图':6s} | {'PNG':6s} | {'图示':5s} | 状态")
print("=" * 100)

for nd in note_dirs:
    mds = glob.glob(os.path.join(BASE, nd, "*.md"))
    imgs = glob.glob(os.path.join(BASE, nd, "imgs", "*.png"))
    screenshots = [i for i in imgs if "diagram_" not in os.path.basename(i)]
    diagram_pngs = [i for i in imgs if "diagram_" in os.path.basename(i)]
    
    sc = len(screenshots)
    dg = len(diagram_pngs)
    total_screenshots += sc
    total_diagrams += dg
    
    md_ok = len(mds) > 0
    has_diagram = False
    if md_ok:
        with open(mds[0], "r") as f:
            content = f.read()
        has_diagram = "结构化图示" in content
    
    status_parts = []
    if md_ok:
        status_parts.append("笔记✅")
    else:
        status_parts.append("笔记❌")
        issues.append(f"{nd}: no md file")
    
    if sc >= 6:
        status_parts.append(f"截图✅{sc}")
    elif sc > 0:
        status_parts.append(f"截图🟡{sc}")
    else:
        if nd.startswith("2026-") and "_第" in nd:
            pass  # offline lesson, no screenshots needed
        else:
            status_parts.append(f"截图❌{sc}")
            issues.append(f"{nd}: missing screenshots ({sc})")
    
    if dg >= 2:
        status_parts.append(f"图示✅{dg}")
    elif dg > 0:
        status_parts.append(f"图示🟡{dg}")
    elif has_diagram:
        status_parts.append(f"图示🟡JSON")
    else:
        status_parts.append(f"图示❌")
        issues.append(f"{nd}: no diagrams")
    
    status = " | ".join(status_parts)
    print(f"{nd:55s} | {'✅' if md_ok else '❌':4s} | {sc:5d} | {dg:5d} | {'✅' if has_diagram else '❌':5s} | {status}")

print("=" * 100)
print(f"总计: {len(note_dirs)} 篇笔记 | {total_screenshots} 张截图 | {total_diagrams} 张图示PNG")
if issues:
    print(f"\n⚠️ 发现 {len(issues)} 个问题:")
    for i in issues:
        print(f"  - {i}")
else:
    print("✅ 全部正常！")
