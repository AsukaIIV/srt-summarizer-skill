# CLAUDE.md — SRT-SUMMARIZER Skill 仓库指引

## 项目定位

这是一个 Claude Code Skill 仓库，将课堂字幕/转录文本整理为结构化 Markdown 课堂笔记。Skill 入口为 `SKILL.md`，辅助脚本在 `scripts/` 目录下。

## 核心原则

- **Skill 的 LLM 是 Claude 自身** —— 不需要外部 API 调用，笔记生成完全由 Claude 完成
- **辅助脚本负责确定性任务** —— 文件扫描、SRT 解析、视频抽帧、图示渲染、Markdown 组装，都是 Claude 做不好或不应浪费上下文去做的事情
- **可选依赖优雅降级** —— opencv-python 和 Pillow 不可用时给出清晰提示，不崩溃
- **`prompts/system.md` 是最核心的资产** —— 定义了输出质量标准和五段结构

## 文件职责

| 文件 | 职责 | 修改注意 |
|------|------|----------|
| `SKILL.md` | Skill 定义 + 工作流指令 | 面向 Claude 的指令，不是面向用户的文档 |
| `prompts/system.md` | 笔记生成系统提示词 | 定义五段结构、禁止项、格式规范、自检清单 |
| `scripts/scanner.py` | 目录扫描 + 字幕视频配对 | Jaccard 相似度配对逻辑，无状态纯函数 |
| `scripts/parse_srt.py` | SRT 时间轴解析 + 质量评估 | 8 维评分系统，质量引导指令生成 |
| `scripts/video_frames.py` | 视频关键帧提取 | 需 opencv-python，无则优雅降级 |
| `scripts/diagram_renderer.py` | 结构化图示 JSON 提取 + PNG 渲染 | 需 Pillow，支持 comparison/flow/formula_map 三种模板 |
| `scripts/writer.py` | Markdown 组装 + 图片语义注入 + 文件写出 | 注入策略：锚点替换 → 章节匹配 → 末位附录 |
| `scripts/_utils.py` | 共享工具函数 | `format_seconds` 和 `sanitize_filename`，所有脚本共用 |
| `fonts/` | 中文字体 | 渲染图示用，缺字体时降级为系统字体 |

## 编辑约定

- Python 脚本使用 Python 3.10+ 语法，类型注解使用 `list[dict]` 而非 `List[Dict]`
- 所有脚本可独立运行（`python3 scripts/xxx.py`），也支持 `from scripts.xxx import func` 导入
- 共享函数放在 `_utils.py`，不要在脚本间交叉导入彼此的函数
- 脚本输出到 stdout，警告和错误输出到 stderr
- 字符编码统一 UTF-8

## 质量评估系统

`parse_srt.py` 的 `assess_quality()` 返回 8 维评分（0-100）：

1. 乱码/编码错误检测
2. 断句完整性（不以句末标点结尾的比例）
3. 语气填充词密度（um/uh/嗯/呃等）
4. 重复词密度
5. 纯噪音行比例
6. 分段时长异常（过短 <0.3s / 过长 >30s）
7. 文本密度 + CJK 比例
8. 内容重复度

评分区间：≥75 good | 45-74 medium | <45 poor。`quality_guidance()` 根据等级返回策略指令。

## 不做什么

- 不添加 GUI / Web Server / API 管理层
- 不引入新的外部依赖（除非有充分理由）
- 不修改 `prompts/system.md` 的五段结构（一～五）和段名
- 不让辅助脚本承担 LLM 任务（如文本摘要、内容理解）
- 不在 `_utils.py` 中引用其他脚本模块
