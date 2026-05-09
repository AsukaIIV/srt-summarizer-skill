---
name: srt-summarizer
description: >
  将课堂字幕(.srt)、转录文本(.txt/.md)和视频整理为结构化 Markdown 课堂笔记。
  支持 SRT 时间轴解析、视频截图提取、结构化图示渲染(comparison/flow/formula_map)、
  图文混排和五段式笔记输出。典型触发场景：用户提供字幕文件路径或课程资料目录，
  要求整理成课堂笔记、听课总结、复习资料。
---

# SRT-SUMMARIZER Skill

AI 驱动的课堂录播整理工具。把字幕、转录文本和视频整理成结构化的五段式 Markdown 课堂笔记。

## 触发示例

- `/srt-summarizer ~/courses/physics101/`
- `/srt-summarizer lesson1.srt`
- `/srt-summarizer lecture1.srt lecture1.mp4`
- `帮我把这个文件夹里的课堂字幕整理成笔记`
- `把 lesson.srt 总结为课堂笔记`

## 依赖检查

本 skill 的辅助脚本在 `scripts/` 目录下。首次使用前，建议检查可选依赖：

```bash
# 核心依赖（Python 3.10+ 标准库，无需安装）
python3 -c "import re, os, json, datetime; print('核心依赖 OK')"

# 可选：视频截图提取
pip install opencv-python   # 不需要视频抽帧可跳过

# 可选：结构化图示渲染
pip install Pillow           # 不需要图示渲染可跳过
```

## 工作流

### 第一步：扫描输入

用户提供一个路径（文件或目录）。调用 `scripts/scanner.py` 扫描：

```bash
python3 scripts/scanner.py <target_path>
```

或者直接在 Python 中调用：

```python
from scripts.scanner import scan_and_pair
result = scan_and_pair(target_path)
```

`scan_and_pair()` 返回：

```python
{
    "transcripts": [...],   # 发现的字幕/文本文件
    "videos": [...],        # 发现的视频文件
    "lessons": [            # 配对结果
        {
            "lesson_id": str,
            "transcript_path": str,
            "video_path": str,    # 可能为空字符串
            "source_label": str,
        }
    ],
    "is_directory": bool,
    "directory": str,
}
```

将扫描结果展示给用户确认。如果发现多个课程，询问用户：
- 全部处理
- 指定处理其中几个
- 是否添加往期笔记文件作为上下文

### 第二步：解析字幕

对每个 lesson，调用 `scripts/parse_srt.py` 解析字幕内容：

```python
from scripts.parse_srt import parse_srt_text, parse_srt_segments

transcript = parse_srt_text(lesson["transcript_path"])
segments = parse_srt_segments(lesson["transcript_path"])
```

`parse_srt_text()` 返回带时间戳的转录文本（适合直接放入 prompt）。
`parse_srt_segments()` 返回结构化分段列表（供视频抽帧和质量评估使用）。

#### 第二步附加：字幕质量评估

解析完成后，**必须运行质量评估**，根据结果调整生成策略：

```python
from scripts.parse_srt import assess_quality, quality_guidance

report = assess_quality(segments)
print(report.summary())          # 单行摘要，如 "✗ 字幕质量：poor (评分 40/100)"
guidance = quality_guidance(report)  # 质量引导指令，good 时为空
```

报告检测的问题类型：
- **乱码/编码错误**：Unicode 替换字符、混合编码痕迹
- **断句问题**：不以句末标点结尾的段过多（ASR 按时间窗口切分导致）
- **语气填充词**：um/uh/嗯/呃 等
- **重复词**：ASR 卡顿产生的重复
- **纯噪音行**：仅含符号数字的行
- **时长异常**：过短碎片段（<0.3s）或过长段（>30s）

得分范围 0-100，分为三档：
| 评分 | 等级 | 策略 |
|------|------|------|
| ≥80 | good | 正常生成，无额外限制 |
| 50-79 | medium | 保守生成，加强 `[unclear]` 标注，图示降低要求 |
| <50 | poor | 严格限制：禁止硬猜术语、要求跨段拼接语义、**不输出**结构化图示、缺失内容显式标注 |

`quality_guidance()` 返回的指令**必须原样拼接**到最终 prompt 的转录文本之前。

#### 第二步附加：领域分类

质量评估完成后，**必须运行领域分类器**，判断课程属于 STEM 还是社会科学，以调整生成策略：

```python
from scripts.parse_srt import classify_domain, domain_guidance

domain_report = classify_domain(
    segments,
    course_name=course_name,
    transcript_path=lesson["transcript_path"],
)
print(domain_report.summary())        # 如 "领域分类：社科/人文 (置信度 85%)"
domain_guide = domain_guidance(domain_report)  # STEM 时为空字符串
```

分类基于三路加权信号：
1. 课程名关键词匹配（权重 3x）
2. 字幕内容关键词采样（权重 1x，采样 200 段）
3. 文件名关键词匹配（权重 2x）

`domain_guidance()` 对 STEM 返回空字符串（`system.md` 已为 STEM 优化），对社科类返回正文要素替换、考试栏目调整、图示类型偏好等指令。`domain_guidance()` 返回的指令**必须在 quality_guidance 之后、转录文本之前**拼接到 prompt 中。

### 第三步：提取视频截图（可选）

如果 lesson 有配对的视频且用户需要图文混排：

```python
from scripts.video_frames import extract_frames

saved_paths, frame_items = extract_frames(
    video_path=lesson["video_path"],
    image_dir=image_dir,
    max_frames=8,
    subtitle_segments=segments,
    course_name=course_name,
)
```

无 opencv 时给出提示并降级为纯字幕模式。

### 第四步：生成课堂笔记（核心）

这是 skill 的核心步骤 —— **由 Claude 自身完成**，不需要调用外部 API。

1. 读取 `prompts/system.md` 作为系统级输出规范
2. 读取转录文本内容
3. 收集课程上下文信息（向用户询问或从文件内容推断）：
   - 课程名称
   - 课程总体要求（可选）
   - 往期笔记内容（可选）
4. 如果有视频截图，生成截图描述文本（含时间戳、内容提示）
5. 按照 `prompts/system.md` 中规定的**五段结构**生成课堂笔记：
   - **一、课程概要**（表格：上课日期、课程名称、本节范围、主讲教师、本节课导言）
   - **二、正文内容**（按讲课顺序分部分，每部分含三级标题知识点）
   - **三、教师强调重点**（引用块格式，逐条列出）
   - **四、作业与考试重点**（作业题目、必考公式汇总表、必记概念清单、答题规范）
   - **五、课程总结**（5-8句脉络概括 + 下节课预告）
6. 如果内容适合，在末尾输出 `## 结构化图示输出` 区块，包含 JSON 格式的图示规格
7. 将质量引导指令（`quality_guidance`）和领域引导指令（`domain_guidance`）拼接后，放在转录文本之前，形成完整的用户 prompt

**重要约束**（已在 system.md 中详细规定）：
- 严格五段结构，不得缺段、并段、重排
- 信息要密、解释要准、层次要稳
- 不臆造内容，不确定处标注 `[unclear]`
- 公式使用行内代码 `` `n₁sinθ₁ = n₂sinθ₂` ``
- 只使用 `##`、`###`、`####` 三级标题

### 第五步：提取并渲染结构化图示

从 Claude 生成的 Markdown 中提取结构化图示 JSON：

```python
from scripts.diagram_renderer import extract_diagram_specs, render_diagram_entries

clean_content, diagram_specs, warnings = extract_diagram_specs(claude_output)
diagram_entries, render_warnings = render_diagram_entries(diagram_specs, image_dir)
```

对每个警告信息，告知用户。

### 第六步：组装并写出输出

```python
from scripts.writer import build_output_paths, write_summary

# lesson_title 由 Claude 根据课堂内容生成，格式建议：
#   {YYYY-MM-DD}_{第X周}_{本节主题}
# save_dir 使用课程文件夹，如 "通信电子线路"
bundle_dir, img_dir, note_path = build_output_paths(
    source_file=lesson["transcript_path"],
    save_dir=output_dir,       # 课程文件夹
    course_name=course_name,
    lesson_title=lesson_title,  # 每节课的目录名和笔记文件名
)

# 合并截图条目和图示条目
all_image_entries = image_entries + diagram_entries

write_summary(
    out_path=note_path,
    source_path=lesson["transcript_path"],
    content=clean_content,
    image_entries=all_image_entries,
)
```

### 第七步：汇报结果

输出最终结果摘要，包括：
- 成功/失败数量
- 每个课程的输出目录和文件路径
- 生成时间
- 字符统计
- 如有警告（图示渲染失败、截图提取不足等），一并列出

## 多课程批量处理

当用户提供的是一个包含多个字幕文件的目录时：

1. 先展示扫描结果（所有发现的课程配对）
2. 询问用户是否批量处理，或选择其中几个
3. 如果批量处理，逐个课程执行第二步到第六步
4. 可以询问用户是否使用统一的课程名和总体要求
5. 每处理完一个课程输出进度

## 输出目录结构

**每节课必须独立目录**，保证笔记多了之后便于管理。课程文件夹为顶层容器，每节课在该文件夹内拥有独立子目录：

```text
{课程名}/
└── {课程目录名}/
    ├── {课程目录名}.md
    └── imgs/
        ├── 2026-05-08_课程名_001_frame-hh-mm-ss.png  # 课堂截图
        └── diagram_01_comparison.png                  # 结构化图示
```

- `{课程名}`：课程文件夹，同一课程的所有笔记都在此目录下
- `{课程目录名}`：每节课的独立子目录，命名建议为 `{YYYY-MM-DD}_{第X周}_{本节主题}`
- 笔记 `.md` 文件与 `imgs/` 平级放在该子目录内

示例：

```text
通信电子线路/
├── 2026-03-31_第5周_丙类谐振功放直流馈电与偏置电路/
│   ├── 2026-03-31_第5周_丙类谐振功放直流馈电与偏置电路.md
│   └── imgs/
│       └── diagram_01_comparison.png
└── 2026-04-07_第6周_倍频器与D类功放/
    ├── 2026-04-07_第6周_倍频器与D类功放.md
    └── imgs/
        └── diagram_01_flow.png
```

默认输出到当前工作目录。用户可指定输出目录。

## 注意事项

- 首次使用建议先用一节较短课程测试
- 转录质量较差的内容（如机器听写有大量错误），应在 prompt 中提醒 Claude 标注 `[unclear]`
- 视频任务无有效截图时应报告失败（不降级为纯文本），因为截图是用户特意提供的教学材料
- 纯字幕文件无需视频，直接生成纯文本笔记
- 如果用户指定了往期笔记文件，应在 prompt 中包含其内容以保持课程连续性

## 常见问题

### Pillow 未安装（结构化图示无法渲染）

```
Pillow 未安装，跳过图示渲染。请运行: pip install Pillow
```

**解决**：`pip install Pillow`。不影响笔记正文生成，只是没有结构化对比图/流程图/公式图。

### opencv-python 未安装（视频截图无法提取）

```
opencv-python 未安装。请运行: pip install opencv-python
```

**解决**：`pip install opencv-python`。不影响纯字幕模式，视频文件会被跳过。

### 中文字体找不到（图示中出现方块字或乱码）

**解决**：确保 `fonts/HarmonyOS_Sans_SC_Medium.ttf` 存在。Pillow 会依次尝试：项目内字体 → 系统 PingFang/STHeiti → NotoSansCJK → 默认字体。

### 字幕质量报告显示 "poor"

**原因**：ASR 转录质量极差（大量乱码、无标点、纯噪音段）。  
**解决**：skill 会自动注入保守生成策略（强制标注 `[unclear]`、不输出图示、要求跨段拼接语义）。如果报告明显不准确，检查字幕文件编码是否为 UTF-8。

### 单文件模式下找不到视频

**解决**：将字幕和视频放在同一目录下，确保文件名至少部分匹配（如 `lesson1.srt` + `lesson1.mp4`）。完全不同的文件名不会被配对。
