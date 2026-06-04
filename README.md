# SRT-Summarizer

AI 驱动的课堂录播整理工具。将字幕文件（.srt）、转录文本（.txt/.md）和视频整理为结构化 Markdown 课堂笔记。

## 用法

```bash
# 处理单个字幕文件或整个目录
python3 scripts/scanner.py ~/courses/光纤通信/
python3 scripts/scanner.py lesson1.srt

# 批量生成笔记（直接调 API，绕过模型限制）
python3 scripts/generate_gaoshu.py \
  --srt-dir /path/to/srt \
  --out-dir /path/to/output \
  --course "课程名"
```

## 工作流

```
SRT字幕 → 质量评估 → 领域分类 → 视频截图(可选) → 笔记生成 → LaTeX知识地图 → Obsidian集成
```

### 输出结构（五段式笔记）

1. **一、课程概要** — 日期/课程/范围/教师/导言表格
2. **二、正文内容** — 按讲课顺序分部分，每知识点六要素展开（定义→公式→推导→例题→注意点）
3. **三、教师强调重点** — 引用块格式
4. **四、作业与考试重点** — 作业题/必考公式/必记概念/答题规范
5. **五、课程总结** — 脉络概括 + 下节课预告

### 超详细模式（默认标准 2026-06+）

- 每章开头：`$$\begin{array}{c}...\end{array}$$` 知识地图（LaTeX array，非 JSON）
- 每知识点：定义→公式→推导→例题→注意事项 六要素展开
- 每章 ≥8 道完整求解例题（step-by-step）
- 题型总览表 + 易错点汇总 + 常用结论速查 三表齐全
- 每节末尾：LaTeX 知识结构图（`\downarrow` 流向，`\swarrow \searrow` 分支）
- 公式统一 LaTeX（`$...$` / `$$...$$`），Unicode 数学符号自动转义
- 禁止 backtick 代码块写公式、禁止 JSON 结构化图示

### 知识地图规则

结构化图示使用 LaTeX `array` 环境（**不是 JSON**）：

```latex
$$\begin{array}{c}
\text{知识点A} \\
\downarrow \\
\text{知识点B} \\
\swarrow \searrow \\
\text{子知识C} \quad \text{子知识D}
\end{array}$$
```

- `\downarrow` = 纵向归属/流向
- `\swarrow \searrow` = 分支
- 紧凑格式：`$$` 与 `\begin{array}` 之间无换行
- 后处理脚本 `scripts/render_all.py` 自动将旧 JSON 图示转为 LaTeX array

### 输入源

| 类型 | 说明 |
|------|------|
| `.srt` | 字幕文件（标准 SRT 格式） |
| `.txt` / `.md` | 转录文本 |
| `.pdf` | 课堂讲义（自动 pdftotext / markitdown / pymupdf 提取） |
| `.m4a` / `.mp3` | 原始录音 → 用 `scanner.find_audio_transcripts()` 配对已有 SRT |

**本工具不执行语音转文字（ASR）。** 用户必须先自行将录音/视频转为 SRT 字幕。

## 脚本列表

| 脚本 | 用途 |
|------|------|
| `scanner.py` | 扫描目录、配对字幕/视频/音频、自动 m4a→srt 匹配 |
| `parse_srt.py` | 解析 SRT + 质量评估（0-100分）+ 领域分类（STEM/社科） |
| `writer.py` | 组装并写出五段式笔记 |
| `video_frames.py` | 从视频提取截图帧 |
| **`generate_gaoshu.py`** | ⭐ 批量生成脚本：按章分组→≤20KB分块→v4-pro API调用→合并 |
| **`batch_prepare.py`** | ⭐ 批量准备（CLI参数化：`--course` `--offline-dir` `--out-dir`） |
| `render_all.py` | 后处理：JSON图示→LaTeX array、修复路径、清理格式 |
| `convert_latex_cleanup.py` | Unicode→LaTeX 公式转换（支持自定义路径） |
| `verify_knowledge_map.py` | 验证 `\begin{array}` / `\end{array}` 配平（支持 `--fix`） |
| `verify.py` | 笔记完整性验证 |
| `generate_from_pdf.py` | PDF 讲义 → 笔记生成 |

## 目录结构

```
srt-summarizer/
├── SKILL.md                    # Agent 技能定义（精简后 288 行）
├── README.md                   # 本文件
├── prompts/
│   └── system.md               # 笔记生成系统提示词（LaTeX array 标准）
├── scripts/                    # 辅助脚本（12个）
│   ├── scanner.py              # 文件扫描 + m4a→srt 配对
│   ├── parse_srt.py            # SRT 解析 + 质量评估 + 领域分类
│   ├── video_frames.py         # 视频截图提取
│   ├── writer.py               # 笔记组装写出
│   ├── render_all.py           # 后处理：JSON→LaTeX array + 路径修复
│   ├── generate_gaoshu.py      # ⭐ 批量 API 生成（可复用）
│   ├── batch_prepare.py        # 批量准备（CLI参数化）
│   ├── convert_latex_cleanup.py # Unicode→LaTeX 转换
│   ├── verify_knowledge_map.py # array 配平验证（--fix）
│   ├── verify.py               # 完整性验证
│   ├── generate_from_pdf.py    # PDF 讲义生成
│   └── _utils.py               # 通用工具函数
└── references/                 # 参考文档（6个）
    ├── batch-processing.md     # 大规模批量处理工作流
    ├── direct-api-generation.md # 直接 API 调用模板（v4-pro）
    ├── delegate-task-template.md # 子代理 save script 模板
    ├── bilibili-course-chapter-grouping.md # B站课程按章分组
    ├── obsidian-post-processing.md # Obsidian 知识库集成
    └── obsidian-latex-css.md   # LaTeX 显示优化 CSS
```

## 依赖

| 依赖 | 用途 | 是否必需 |
|------|------|----------|
| Python 3.10+ | 运行所有脚本 | ✅ 必需 |
| `pip install opencv-python` | 从视频提取截图 | ⚠️ 可选（纯字幕模式跳过） |
| `poppler-utils`（`pdftotext`） | PDF 讲义文本提取 | ⚠️ 可选 |
| `markitdown` / `pymupdf` | PDF 备选提取 | ⚠️ 可选 |

## 批量生成策略

| 规模 | 方法 | 说明 |
|------|------|------|
| ≤5 节 | `delegate_task` 子代理并行 | 每轮 3 个，继承主会话模型 |
| ≥10 节 | 分批并行 | 多轮 delegate_task，每轮 3 个 |

### API 限制应对

- **大 payload 断连**（`Broken pipe`）：输入切 ≤20KB 块
- **间歇性 504**：指数退避重试 6 次（30s→60s→120s→240s→480s→600s）
- **模型名**：代理端 `deepseek-ai/deepseek-v4-pro`，官方 `deepseek-v4-pro`
- **必须走代理**（47.251.108.225:3000），禁止 DeepSeek 官方直连

## 笔记后处理

1. **LaTeX 转换**：`scripts/convert_latex_cleanup.py [目录]`
2. **知识地图验证**：`scripts/verify_knowledge_map.py --fix [目录]`
3. **格式修复**：`scripts/render_all.py --course 课程名`
4. **Obsidian 集成**：补充 YAML frontmatter → MOC 大纲 → Dataview 汇总（见 references/）

## 2026-06 更新

- 结构化图示从 JSON → LaTeX `array` 环境（system.md 已固化）
- `batch_prepare.py` 支持 CLI 参数化（`--course` `--offline-dir` 等）
- 新增 `scanner.find_audio_transcripts()` m4a→srt 配对
- SKILL.md 精简 75%（1149→288 行），重复内容收敛到 references
- `convert_latex_cleanup.py` 通用化 + 补全 40+ Unicode→LaTeX 映射
