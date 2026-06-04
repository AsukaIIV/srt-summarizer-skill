#!/usr/bin/env python3
"""
从 PDF 讲义提取文字 → 调用 LLM 生成超详细笔记
可复用模板：修改 PDF_DIR、chapters 列表即可用于其他课程

前置依赖：
  sudo apt-get install -y poppler-utils   # pdftotext
  # 或：pip install pymupdf              # pymupdf 后备

使用方式：
  1. 修改下面的 PDF_DIR 为讲义目录
  2. 修改 chapters 列表（章节号、输出文件名）
  3. 调整 API_URL/API_KEY/MODEL 为可用端点
  4. python3 generate_from_pdf.py
"""
import os, sys, json, time, urllib.request

# ===== 配置区 =====
PDF_DIR = "/vol2/1000/hdd0/重要文件/obsidian_library/课程录音/微机原理"
OUTPUT_DIR = os.path.join(PDF_DIR, "notes")
API_URL = "https://api.deepseek.com/v1/chat/completions"
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "sk-e76f44fa960d45c49208d1e9ecf465d44")
MODEL = "deepseek-chat"  # v4-flash

chapters = [
    (1, "第1章_text.txt", "微机原理_第1章_微型计算机基础_超详细版.md"),
    (2, "第2章_text.txt", "微机原理_第2章_微处理器结构_超详细版.md"),
    (3, "第3章_text.txt", "微机原理_第3章_指令系统和寻址方式_超详细版.md"),
]

# 也可用精简版 system prompt 以降低 payload
SYSTEM_PROMPT = """你是一位专业的课堂笔记生成专家，输出超详细Markdown课堂笔记。
硬性要求：
1. 超详细级别：每知识点 定义→公式→推导→例题→注意点 六要素完整展开
2. 五段结构：## 一、课程概要 → ## 二、正文内容 → ## 三、教师强调重点 → ## 四、作业与考试重点 → ## 五、课程总结
3. 知识地图：正文开头用 LaTeX array 画知识流向图
4. 题型总览表 + 易错点汇总 + 常用结论速查（齐备）
5. 每章至少8道典型例题的完整求解过程
6. LaTeX公式：行内$...$，块级$$...$$
7. 文末输出 ## 结构化图示输出 + 至少1张 diagram JSON（comparison/flow/formula_map）
8. 基于教材原文，不脱离内容臆造"""
# ===== 配置区结束 =====

def call_llm(user_text, label, max_retries=6):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text}
        ],
        "max_tokens": 16384,
        "temperature": 0.3
    }
    data = json.dumps(payload).encode()
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                API_URL, data=data,
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=600) as resp:
                r = json.loads(resp.read().decode())
                return r['choices'][0]['message']['content']
        except Exception as e:
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] [{label}] 尝试{attempt+1}/{max_retries}: {str(e)[:100]}")
            if attempt < max_retries - 1:
                time.sleep(min(30 * (2 ** attempt), 600))
    return None

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for ch_num, pdf_text_name, outname in chapters:
        pdf_path = os.path.join(PDF_DIR, pdf_text_name)
        if not os.path.exists(pdf_path):
            print(f"跳过：{pdf_path} 不存在")
            continue
        with open(pdf_path, "r", encoding="utf-8") as f:
            text = f.read()
        print(f"第{ch_num}章: {len(text)} chars")
        
        prompt = f"请根据以下教材原文，为《微机原理》第{ch_num}章生成超详细笔记。\n\n## 教材原文\n{text}"
        result = call_llm(prompt, f"第{ch_num}章")
        if result:
            safe_name = outname  # 已在章节名中预处理好
            outfile = os.path.join(OUTPUT_DIR, safe_name)
            with open(outfile, "w", encoding="utf-8") as f:
                f.write(result)
            print(f"✅ 已保存: {outfile}")
        time.sleep(3)
    print("全部完成！")

if __name__ == "__main__":
    main()
