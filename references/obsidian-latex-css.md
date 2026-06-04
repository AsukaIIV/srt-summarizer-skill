# Obsidian LaTeX 显示优化 CSS 片段

将笔记导入 Obsidian 后，若 LaTeX 公式显示不理想（太小、颜色浅、对齐差），可添加 CSS 片段改善渲染。

## 安装方法

1. 在 Obsidian vault 的 `.obsidian/snippets/` 目录下创建 `latex-optimization.css`
2. Obsidian 中打开 **设置 → 外观 → CSS 代码片段**
3. 点击 **刷新** 按钮，然后开启 `latex-optimization`

## 推荐 CSS 内容

```css
/* LaTeX/MathJax 公式字体放大 */
.MJX-TEX {
  font-size: 1.05em !important;
}

/* 行内公式 */
span.math-inline {
  font-size: 1.05em;
}

/* 块级公式居中 + 间距 */
.math-block > mjx-container {
  text-align: center !important;
  margin: 1em 0 !important;
}

/* 暗色主题公式颜色 */
mjx-container mjx-math {
  color: #d4d4d4 !important;
}
.theme-dark .math-block,
.theme-dark .math-inline {
  color: #e0e0e0;
}
```

## 实用调整

| 效果 | CSS 属性 |
|------|---------|
| 放大字体 | `font-size: 1.1em` |
| 加粗公式 | `font-weight: 500` |
| 块间距 | `margin: 1.5em 0` |
| 行内垂直对齐 | `vertical-align: middle` |
