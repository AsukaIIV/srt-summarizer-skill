# Batch Processing Reference

This document records the post-processing repair pipeline discovered during a
27-session batch generation of Communication Electronic Circuits course notes.

## Problem Catalog

When generating 25+ notes via `delegate_task` sub-agents, these issues recur:

| Issue | Symptom | Root Cause | Fix |
|-------|---------|------------|-----|
| Missing screenshots | Note exists but imgs/ empty | `video_frames.py` saves to `未知日期_*` directories, not the note's own `imgs/` | Copy screenshots from matching `未知日期_*` dir |
| Absolute image paths | Screenshots don't render in Obsidian | Sub-agent used absolute path like `/vol2/1000/.../` | Replace with relative `imgs/xxx.png` |

## Repair Pipeline

## Repair Pipeline

Use `scripts/render_all.py` to auto-fix all known issues:

```bash
# Fix a specific course
python3 scripts/render_all.py --course 通信电子线路

# Or target a directory directly
python3 scripts/render_all.py --dir /path/to/notes
```

This handles:
- JSON structured diagrams → LaTeX array knowledge maps
- Absolute paths → relative `imgs/` paths
- Ensures `## 结构化图示输出` is the last section
- Closes unclosed JSON code blocks

For array balance verification:
```bash
python3 scripts/verify_knowledge_map.py --fix /path/to/notes
```

## Standard Diagram JSON Templates

*(JSON structured diagrams are deprecated — system.md now outputs LaTeX `array` directly. This section kept for legacy note conversion reference only.)*

## Verification Checklist

Run after batch processing:
- [ ] Every note has `## 结构化图示输出` as the last section
- [ ] All screenshot paths are relative (`imgs/xxx.png`)
- [ ] `\begin{array}` / `\end{array}` counts are balanced
- [ ] No `未知日期_` references remain in markdown files
- [ ] No trailing whitespace after the last `$$` or content
