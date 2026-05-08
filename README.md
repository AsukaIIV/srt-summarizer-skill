# SRT-SUMMARIZER Skill

AI 驱动的课堂录播整理工具 —— 把字幕、转录文本和视频整理为结构化五段式 Markdown 课堂笔记。

## 这是什么？

这是一个 [Claude Code](https://claude.ai/code) Skill。在 Claude Code 中输入 `/srt-summarizer <字幕文件或目录>`，Claude 会自动完成：

- 解析 SRT 字幕时间轴
- 评估转录质量并调整生成策略
- 提取视频关键截图（可选）
- 生成严格五段式 Markdown 课堂笔记
- 渲染结构化图示（对比图 / 流程图 / 公式图）

输出笔记包含：课程概要 → 正文推导 → 教师强调 → 作业考试重点 → 课程总结，信息密度高、可直接用于复习。

## 快速开始

### 1. 安装

```bash
# 克隆仓库
git clone https://github.com/AsukaIIV/srt-summarizer-skill srt-summarizer-skill

# 注册为 Claude Code Skill（软链接到 skills 目录）
mkdir -p ~/.claude/skills
ln -s "$(pwd)/srt-summarizer-skill" ~/.claude/skills/srt-summarizer
```

重启 Claude Code 后生效。

### 2. 安装可选依赖

```bash
# 核心依赖（Python 3.10+ 标准库，无需安装）
python3 -c "import re, os, json, datetime; print('核心依赖 OK')"

# 可选：视频截图提取
pip install opencv-python

# 可选：结构化图示渲染
pip install Pillow
```

### 3. 使用

在 Claude Code 对话中：

```
/srt-summarizer ~/courses/physics101/          # 处理整个目录
/srt-summarizer lesson1.srt                    # 处理单个字幕文件
/srt-summarizer lecture1.srt lecture1.mp4      # 指定字幕 + 视频
```

## 输出结构

每个课程生成一个独立目录：

```
{文件名}_{来源目录}_{课程名}/
├── {文件名}_{课程名}_课堂总结.md    # 结构化笔记
└── imgs/
    ├── 20260509_课程名_001_frame-12-34-56.png   # 视频截图
    └── diagram_01_comparison.png                # 结构化图示
```

## 适用场景

- 大学课堂录播整理
- 考研/考证培训视频笔记
- 在线课程（MOOC、网课）字幕整理
- 会议录音转录文本结构化

## 字幕质量说明

Skill 会自动评估字幕质量并调整策略：

| 评分 | 等级 | 策略 |
|------|------|------|
| ≥75 | 好 | 正常生成 |
| 45-74 | 中 | 保守生成，加强 `[unclear]` 标注 |
| <45 | 差 | 严格限制，不输出图示，强制标注不确定内容 |

## 项目结构

```
srt-summarizer-skill/
├── SKILL.md              # Skill 定义（Claude Code 加载入口）
├── README.md             # 本文件
├── CLAUDE.md             # Claude 工作区指引
├── requirements.txt      # Python 可选依赖
├── LICENSE               # MIT 许可
├── prompts/
│   └── system.md         # 笔记生成系统提示词
├── scripts/
│   ├── scanner.py        # 目录扫描 + 字幕视频配对
│   ├── parse_srt.py      # SRT 解析 + 质量评估
│   ├── video_frames.py   # 视频关键帧提取
│   ├── diagram_renderer.py # 结构化图示渲染
│   ├── writer.py         # Markdown 组装 + 图片注入
│   └── _utils.py         # 共享工具函数
└── fonts/
    └── HarmonyOS_Sans_SC_Medium.ttf  # 中文字体
```

## 常见问题

### 视频截图提取失败

```
opencv-python 未安装。请运行: pip install opencv-python
```

不影响纯字幕模式，视频文件会被跳过。

### 结构化图示无法渲染

```
Pillow 未安装，跳过图示渲染。请运行: pip install Pillow
```

不影响笔记正文生成，只是没有对比图/流程图/公式图。

### 中文字体乱码

确保 `fonts/HarmonyOS_Sans_SC_Medium.ttf` 存在。渲染器会依次尝试：项目内字体 → 系统 PingFang/STHeiti → NotoSansCJK → 默认字体。

### 字幕质量报告显示"差"

ASR 转录质量极差（大量乱码、无标点、纯噪音段）。Skill 会自动注入保守策略。如果报告明显不准确，检查字幕文件编码是否为 UTF-8。

## 许可

MIT License
