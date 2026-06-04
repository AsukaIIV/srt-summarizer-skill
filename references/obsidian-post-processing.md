# Obsidian Post-Processing Pipeline

After srt-summarizer generates raw notes (five-section markdown), run this
pipeline to integrate them into an Obsidian vault as a browsable, linkable
course knowledge base.

## Vault Path Convention

The Obsidian vault path comes from `OBSIDIAN_VAULT_PATH` in `.env` or from
`memory`. Resolve it before calling any file tools.

## Pipeline Steps

### 0. Confirm Model

The generation step (step 4 of srt-summarizer) benefits from a stronger model.
**Ask the user before switching** from the default model to a more capable one
(e.g., deepseek-v4-pro). If the user has a standing preference to be asked
before any model switch, honour it.

### 1. Input from User

- User provides `.srt` subtitle files (ASR transcription already done — skip this step)
- User may also provide: an output course folder name, existing notes for context,
  PDF filenames for chapter-number mapping

### 2. Generate Notes (srt-summarizer core)

Run the full srt-summarizer workflow for each SRT file. Use a uniform `course_name`
across all lessons in the same course.

### 3. Post-Processing per Note

For each generated `.md` note file:

#### 3a. Supplement YAML Frontmatter

Insert YAML frontmatter at the top of the file, before any existing content:

```yaml
---
chapter: <chapter number extracted, e.g. 4>
section: "<section number, e.g. 4.2>"
title: "<section title>"
date: <YYYY-MM-DD>
tags: [<2-4 Chinese keywords>]
pdf: "<corresponding PDF filename from course material>"
formulas:
  - "<formula 1>"
  - "<formula 2>"
key_points:
  - "<key point 1>"
  - "<key point 2>"
---
```

Sources for each field:
- `chapter`/`section`/`title` — map the srt-summarizer output title against PDF
  filenames in the course material directory to determine chapter number
- `date` — from the SRT filename timestamp
- `tags` — infer from course content
- `pdf` — exact filename match from course PDF directory
- `formulas`/`key_points` — extracted from the "必考公式" table and "必记概念"
  list in the note body (section four of the five-section format)

#### 3b. Rename File by Chapter

Rename from `{YYYY-MM-DD}_{第X周}_{topic}.md` to `{section_number} {title}.md`.

Example:
- `2026-03-31_第5周_丙类谐振功放直流馈电与偏置电路.md`
  → `4.4 直流馈电与偏置电路.md`

Derive the section number by matching the srt-summarizer-generated title against
PDF filenames in the course directory.

If mapping is ambiguous, mark with `[待确认]` and continue processing other files.

Keep both the original directory (from srt-summarizer's output structure) and the
new filename inside it.

### 4. Generate Course MOC (Map of Content)

Scan all generated `.md` files and produce a `课程大纲.md` in the course root
directory inside the vault:

```markdown
# 通信电子线路 · 课程大纲

## 第1章 绪论
- [[1.1 通信系统的组成]]
- [[1.2 通信系统的类型]]
- [[1.3 通信电子线路的基本特点]]

## 第2章 选频网络
- [[2.1 概述]]
- [[2.2 元器件的高频特性]]
- [[2.3 串联谐振回路]]
...
```

Rules:
- Use `[[wikilinks]]` for notes that exist (have been generated)
- Use plain text for chapters/sections that have no note yet
- Chapter list comes from the union of all PDF filenames — treat PDF naming as
  the canonical chapter/section listing

### 5. Generate Dataview Summary Pages (Optional)

These require the Obsidian Dataview community plugin to be installed in the vault.

#### 公式速查.md

```dataview
TABLE without ID section AS "章节", formulas AS "公式"
FROM "课程名"
WHERE formulas
FLATTEN formulas
SORT section ASC
```

#### 考试重点.md

```dataview
TABLE without ID section AS "章节", key_points AS "核心知识点"
FROM "课程名"
WHERE key_points
FLATTEN key_points
SORT section ASC
```

### 6. Output Structure

Final directory layout inside the Obsidian vault:

```text
课程录音/{CourseName}/
├── 课程大纲.md
├── 公式速查.md
├── 考试重点.md
├── 2026-03-31_第5周_丙类谐振功放直流馈电与偏置电路/
│   ├── 4.4 直流馈电与偏置电路.md
│   └── imgs/
│       └── ...
├── 2026-04-07_第6周_倍频器与D类功放/
│   ├── 4.5 倍频器.md
│   └── imgs/
│       └── ...
└── ...
```

## Pitfalls

- **No SRT provided**: User must provide `.srt` files. The script does NOT do ASR
  transcription. If the user only has `.m4a`/`.mp3`/`.mp4` files, tell them to
  transcribe first before using this pipeline.
- **Chapter mapping misses**: When the srt-summarizer title doesn't clearly match
  any PDF filename, mark the file `[待确认]` and flag it in the summary. Do NOT
  block the entire pipeline on one ambiguous file.
- **Missing Dataview plugin**: The formula/quiz summary pages will render as
  plain code blocks instead of live tables. Note this in the output summary.
- **Existing notes**: If a chapter note already exists (e.g. `4.2 丙类功放.md`),
  do NOT regenerate it. Only supplement its YAML frontmatter and verify naming.
