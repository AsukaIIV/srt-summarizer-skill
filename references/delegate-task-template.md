# 子代理生成笔记的 Save Script 模板

## 背景
使用 `delegate_task` 让子代理生成笔记时，需要提供一个可执行的 Python 脚本模板让子代理保存结果。子代理自动继承主会话模型。

## 模板结构

```python
import sys, os
sys.path.insert(0, '/home/user/.hermes/skills/srt-summarizer')
from scripts.writer import build_output_paths, write_summary

SRT='SRT文件绝对路径'
OUT='输出基目录路径'
TITLE='YYYY-MM-DD_第X周_本节主题'

note_content = '''笔记正文内容'''

bundle_dir, img_dir, note_path = build_output_paths(
    source_file=SRT, save_dir=OUT, course_name='课程名', lesson_title=TITLE
)
write_summary(out_path=note_path, source_path=SRT, content=note_content)
print(f'SAVED:{note_path}')
```

## 实战陷阱

### 子代理实际行为 vs 预期

实践中发现的子代理常见偏差：

| 预期行为 | 实际表现 |
|---------|---------|
| 执行 save script（terminal）保存 | 直接用 write_file 保存，跳过脚本 |
| 严格遵循 system.md 五段格式 | 用 # 一级标题、缺段、合并段 |
| 生成后输出 SAVED:路径 | 不输出，需要主代理自己找文件 |
| 使用 LaTeX $...$ 格式 | 用 $$ 块级或行内代码 `` |

### 应对策略

1. **不要依赖子代理执行保存脚本**。直接在 context 中给绝对路径，让子代理用 write_file 写入
2. **在 context 中显式重复格式要求**，不要只靠 system.md
3. **每轮结束后检查文件开头**验证格式，不达标的重做

### 子代理配置要点 必须包含 `["terminal", "file"]`——需要 `read_file` 加载 SRT 和 system.md，需要 `terminal` 执行保存脚本
2. **不要在 context 里传完整 SRT 内容**——子代理自己用 `read_file` 读取，避免 context 过大
3. **system.md 也要让子代理自己读**：`先读取 /home/user/.hermes/skills/srt-summarizer/prompts/system.md 了解五段式笔记格式规范`
4. **LaTeX 偏好直接在 context 里说**：不用修改 system.md，子代理遵守 context 指令优先于 system.md
5. **title 要告诉子代理生成后填入**：`TITLE='YYYY-MM-DD_第X周_根据内容确定标题'`，子代理根据课程内容替换
6. **子代理可能用 write_file 而非 terminal** 来保存 note_content——两种方式都要支持

## 验证输出

保存后子代理应输出 `SAVED:路径`，主代理据此确认文件位置。
