---
name: srt-summarizer
description: >
  将课堂字幕(.srt)、转录文本(.txt/.md)和视频整理为结构化 Markdown 课堂笔记。
  支持 SRT 时间轴解析、视频截图提取、五段式笔记输出。
  典型触发场景：用户提供字幕文件路径或课程资料目录，
  要求整理成课堂笔记、听课总结、复习资料。
---

# SRT-SUMMARIZER Skill

AI 驱动的课堂录播整理工具。把字幕、转录文本和视频整理成结构化的五段式 Markdown 课堂笔记。

## 输入约定

**本 skill 不执行语音转文字（ASR）。** 用户必须自行提供 `.srt`（字幕文件）、`.txt`
或 `.md`（转录文本）。如果用户只提供了录音/视频文件（`.m4a`/`.mp3`/`.mp4`），
告知用户先完成 ASR 转写。

### 扩展输入：PDF 文件处理

用户可能提供 PPT 转 PDF 格式的课堂讲义。**不要直接用 LLM 臆造内容**——必须先用
工具提取文本：

```bash
# 首选：poppler-utils
sudo apt-get install -y poppler-utils
pdftotext -layout 讲义.pdf 讲义_text.txt

# 次选：markitdown
pip install markitdown && markitdown 讲义.pdf > 讲义_text.txt

# 三选：pymupdf OCR
pip install pymupdf
python3 -c "import fitz; doc=fitz.open('讲义.pdf'); [print(f'--- 第{i+1}页 ---', page.get_text()) for i,page in enumerate(doc)]"
```

提取后的文本（30KB-60KB/章）可直接作为 LLM 上下文。

## 工作流

### 第一步：扫描输入

用户提供一个路径（文件或目录）。调用 `scripts/scanner.py` 扫描：

```bash
python3 scripts/scanner.py <target_path>
```

`scan_and_pair()` 返回配对的字幕/视频信息展示给用户确认。

### 第二步：解析字幕

```python
from scripts.parse_srt import parse_srt_text, parse_srt_segments
transcript = parse_srt_text(lesson["transcript_path"])
segments = parse_srt_segments(lesson["transcript_path"])
```

#### 字幕质量评估（必做）

```python
from scripts.parse_srt import assess_quality, quality_guidance
report = assess_quality(segments)
guidance = quality_guidance(report)  # good→"" / medium→保守 / poor→严格限制
```

`guidance` 返回的指令**必须原样拼接**到最终 prompt 的转录文本之前。

#### 领域分类（必做）

```python
from scripts.parse_srt import classify_domain, domain_guidance
domain_report = classify_domain(segments, course_name=..., transcript_path=...)
domain_guide = domain_guidance(domain_report)  # STEM→"" / 社科→调整要素
```

`domain_guide` 在 `quality_guidance` 之后、转录文本之前拼接到 prompt。

### 第三步：提取视频截图（可选）

```python
from scripts.video_frames import extract_frames
saved_paths, frame_items = extract_frames(
    video_path=..., image_dir=..., max_frames=8,
    subtitle_segments=segments, course_name=...,
)
```

### 第四步：生成课堂笔记（核心）

使用 **`delegate_task` 子代理模式**（子代理继承主会话模型，保持一致）：

```python
delegate_task(
    goal="生成课堂笔记（超详细五段式）",
    context="SRT路径 + 质量评估 + 领域分类结果 + 课程信息 + system.md路径",
    toolsets=["terminal", "file"],
)
```

子代理的 toolset 必须为 `["terminal", "file"]`。子代理用 `read_file` 加载 SRT
和 system.md，用 `terminal` 或 `write_file` 保存结果。

> 子代理自动继承主会话的模型，不需要折腾换模型。同一模型跑到底。

#### 生成粒度决策

扫描完输入后，根据文件数量判断生成粒度：

**① 少量文件（≤5 个）** → 直接按课时生成
- 每个文件对应一节课，逐节生成独立笔记
- 无需询问用户，默认执行

**② 成体系文件（≥6 个）** → 先询问用户
- 扫描结果展示给用户后，直接提问生成粒度：
  - **按课时**：每个 SRT 文件生成一篇独立笔记（适合散课）
  - **按章节**：按文件名中的章节号（如 `【第1章】`）分组合并，每章生成一篇笔记（适合完整课程）
  - **指定脉络**：用户自定分组规则，按指定方式生成

示例：在回复中直接问用户「共发现 N 节课，你想按课时逐节生成、按章节合并生成，还是指定其他分组方式？」

按章节分组时，用 `scripts/scanner.py` 中的章节正则匹配逻辑：
```python
import re
m = re.search(r'【第(\d+)章】', filename)
chapter = f"第{m.group(1)}章" if m else "其他"
```

#### 五段式笔记结构（system.md 中已固化）

1. **一、课程概要** — 表格：日期、课程名、范围、教师、导言
2. **二、正文内容** — 逐知识点展开（定义→公式→推导→例题→注意事项）
3. **三、教师强调重点** — 引用块格式
4. **四、作业与考试重点** — 作业题、必考公式、必记概念、答题规范
5. **五、课程总结** — 5-8 句脉络概括 + 下节课预告

**超详细默认标准（2026-06 起固化）**：

- 知识地图：正文开头 `$$\begin{array}{c}...\end{array}$$` 紧凑格式
- 六要素展开：每知识点 定义→公式→推导→例题→注意点
- 例题每章≥8道，step-by-step
- 题型总览表 + 易错点汇总 + 常用结论速查 齐全
- 每节末尾输出 LaTeX array 知识地图
- 所有公式 LaTeX（`$...$` / `$$...$$`），禁止 backtick
- Unicode 数学符号（λ, μ, θ, ω, η, ≈, ·, ½, √ 等）转 LaTeX 命令

#### 知识地图规则（用户偏好）

在 `## 结构化图示输出` 区块下输出 LaTeX `array` 知识地图（**不是 JSON**）：

```latex
$$\begin{array}{c}
\text{知识点A} \\
\downarrow \\
\text{知识点B} \\
\swarrow \searrow \\
\text{子知识C} \quad \text{子知识D}
\end{array}$$
```

- `\downarrow` 表示纵向归属/流向，`\swarrow \searrow` 表示分支
- 紧凑格式：`$$` 与 `\begin{array}` 之间无换行

### 第五步：写出输出

```python
from scripts.writer import build_output_paths, write_summary

bundle_dir, img_dir, note_path = build_output_paths(
    source_file=..., save_dir=..., course_name=..., lesson_title=...,
)
write_summary(out_path=note_path, source_path=..., content=clean_content)
```

### 第六步：汇报结果

**汇报前验证文件真实存在。** 先 `ls` 确认实际文件再制成表格汇报。

### 第七步：验证输出格式（必做）

所有子代理生成完毕后，主代理必须运行验证脚本检查目录结构与命名规范：

```bash
python3 scripts/verify_output_structure.py <输出基目录>/<课程名>/
```

验证脚本检查三项：

| 检查项 | 规范要求 | 违规级别 |
|--------|---------|---------|
| 文件夹命名 | `YYYY-MM-DD_第X周_主题` | 错误 ❌ |
| .md 文件名 | 与文件夹同名 | 警告 ⚠ |
| imgs/ 子目录 | 每个笔记目录下含 `imgs/` | 警告 ⚠ |

**处理规则：**

- **有错误（❌）**：命名违规的目录必须修正。主代理直接 `mv` 重命名违规目录，**同时重命名目录内对应的 .md 文件**（目录名和 .md 文件名必须一致）。使其符合 `YYYY-MM-DD_第X周_主题` 格式。
- **有警告（⚠）**：逐项检查并修复。特别注意 **目录名改了但 .md 文件名没改** 的情况——两者必须同步。同时检查缺失的 `imgs/` 目录，修复后重新验证。
- **全部通过（✅）**：进入最终汇报。

修复后重新运行验证脚本确认 `✅ 全部验证通过！`。

> 常见遗漏：主代理重命名了文件夹但忘记重命名里面的 .md 文件。验证脚本会明确提示 `.md 文件名不匹配`，修正时务必 `mv 旧名.md 新名.md`。

> 这个验证是**主线代码执行**，不是子代理行为——确保无论子代理产生什么输出，
> 最终交给用户的目录结构都是规范的。

## 输出目录结构

```
{课程名}/
└── {YYYY-MM-DD_第X周_本节主题}/
    ├── {YYYY-MM-DD_第X周_本节主题}.md
    └── imgs/
        ├── {date}_frame-hh-mm-ss.png
        └── diagram_01_comparison.png
```

## 已知陷阱与应对（详细版见 `references/batch-processing.md`）

### 代理 API 限制
- **大 payload 断连**：单次请求≥~100KB 可能 `Broken pipe`，切 ≤20KB 块
- **间歇性 504**：与 payload 大小无关，指数退避重试 6 次（30s→60s→120s→240s→480s→600s）
- **禁止 DeepSeek 官方直连**，全部走代理 47.251.108.225:3000
- **组级缓存策略**：`_cache` 目录逐组缓存，中断可续跑

### delegate_task 问题
- 子代理格式偏差（用 # 一级标题、缺段、$$ 块级而非行内）→ context 中显式重复约束
- 子代理可能用 write_file 而非执行脚本 → 两种保存方式都支持
- 子代理 600s 超时不适用 5+ 组章节 → 分批并行（每轮 ≤3 个子代理）

### 文件名安全
章节名中的 `/` 会炸文件路径，必须替换为 `_`：
`safe_title = title.replace("/", "_").replace("\\", "_")`

### 后处理修复
批量生成后运行 `scripts/render_all.py` 自动修复格式（JSON图示→LaTeX array、路径修正）。
- 替换 JSON 结构化图示为 LaTeX array
- 修复绝对路径为相对路径 `imgs/`
- 确保 `## 结构化图示输出` 在文件末尾

验证 `\begin{array}` / `\end{array}` 配平用 `scripts/verify_knowledge_map.py --fix`。

### 知识地图公式验证
笔记生成后检查 `$$` 块中的 `array` 配平：
```bash
# 精确检查
python3 -c "
import re
with open('笔记.md') as f: text = f.read()
for i, block in enumerate(re.findall(r'\$\$(.*?)\$\$', text, re.DOTALL)):
    b = block.count(r'\begin{array}'); e = block.count(r'\end{array}')
    if b != e: print(f'块#{i}: begin={b} end={e}')
"
# 修复过度 \quad 填充
python3 -c "
import re,sys; path=sys.argv[1]
with open(path) as f: text=f.read()
text=re.sub(r'(\\\\quad\s*){4,}',' \\\\quad ',text)
with open(path,'w') as f: f.write(text)
" 笔记.md
```

## 多课程批量处理

### 小规模（≤5节）：delegate_task 并行
每轮 3 个并行子代理。context 中给 SRT 路径、system.md 路径、保存脚本模板。

### 大规模（≥10节）：分批并行
每轮 3 个子代理，分多轮处理。子代理自动继承主会话模型。
```bash
python3 scripts/batch_prepare.py \
  --course 光纤通信 \
  --offline-dir /path/to/srt \
  --out-dir /path/to/output
```

### B站/网络课大量小SRT
**最优策略**：按章节合并 SRT → 按章生成笔记。详见 `references/bilibili-course-chapter-grouping.md`。

## Obsidian 集成后处理

srt-summarizer 输出的五段式 Markdown 笔记可加工为 Obsidian 结构化知识库
（YAML frontmatter → 课程大纲 MOC → Dataview 汇总页）。
详见 `references/obsidian-post-processing.md`。LaTeX 显示优化 CSS 见 `references/obsidian-latex-css.md`。

## LaTeX 公式转换

笔记中的 Unicode 数学字符需转换为 LaTeX 命令。`scripts/convert_latex_cleanup.py`
自动处理，支持自定义路径：
```bash
python3 scripts/convert_latex_cleanup.py /path/to/notes/
```

常见映射：`λ→\lambda`、`μ→\mu`、`θ→\theta`、`ω→\omega`、`η→\eta`、
`≈→\approx`、`·→\cdot`、`½→\frac{1}{2}`、`√→\sqrt{}`、`₁→_{1}`、`²→^{2}`

## 笔记后处理：思维导图 & 背诵清单

笔记生成后，基于已生成的超详细笔记生成配套材料。用 `delegate_task` 处理即可。

## 依赖检查

```bash
# 核心依赖（Python 3.10+ 标准库）
python3 -c "import re, os, json, datetime; print('OK')"
# 可选：视频截图
pip install opencv-python
```

## 注意事项

- 首次使用建议先用一节较短课程测试
- 转录质量差的内容，prompt 中提醒标注 `[unclear]`
- 子代理的 toolset 必须是 `["terminal", "file"]`
- 保存脚本模板详见 `references/delegate-task-template.md`
