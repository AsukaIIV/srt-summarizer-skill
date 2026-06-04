"""Final cleanup: remove backtick+$ double-wrapping, convert remaining stragglers,
and replace Unicode math characters with LaTeX commands.

Usage:
    # Default: scan 通信电子线路
    python3 scripts/convert_latex_cleanup.py

    # Custom path
    python3 scripts/convert_latex_cleanup.py /path/to/notes/dir
"""

import os, glob, re, sys

# Unicode → LaTeX mapping (comprehensive)
UNICODE_TO_LATEX = {
    # Greek lowercase
    '\u03b1': r'\alpha',     # α
    '\u03b2': r'\beta',      # β
    '\u03b3': r'\gamma',     # γ
    '\u03b4': r'\delta',     # δ
    '\u03b5': r'\varepsilon', # ε
    '\u03b6': r'\zeta',      # ζ
    '\u03b7': r'\eta',       # η
    '\u03b8': r'\theta',     # θ
    '\u03b9': r'\iota',      # ι
    '\u03ba': r'\kappa',     # κ
    '\u03bb': r'\lambda',    # λ
    '\u03bc': r'\mu',        # μ
    '\u03bd': r'\nu',        # ν
    '\u03be': r'\xi',        # ξ
    '\u03bf': r'o',          # ο (omicron = Latin o)
    '\u03c0': r'\pi',        # π
    '\u03c1': r'\rho',       # ρ
    '\u03c3': r'\sigma',     # σ
    '\u03c4': r'\tau',       # τ
    '\u03c5': r'\upsilon',   # υ
    '\u03c6': r'\phi',       # φ
    '\u03c7': r'\chi',       # χ
    '\u03c8': r'\psi',       # ψ
    '\u03c9': r'\omega',     # ω
    # Greek uppercase
    '\u0393': r'\Gamma',     # Γ
    '\u0394': r'\Delta',     # Δ
    '\u0398': r'\Theta',     # Θ
    '\u039b': r'\Lambda',    # Λ
    '\u039e': r'\Xi',        # Ξ
    '\u03a0': r'\Pi',        # Π
    '\u03a3': r'\Sigma',     # Σ
    '\u03a6': r'\Phi',       # Φ
    '\u03a8': r'\Psi',       # Ψ
    '\u03a9': r'\Omega',     # Ω
    # Math symbols
    '\u2248': r'\approx',    # ≈
    '\u2260': r'\neq',       # ≠
    '\u2264': r'\leq',       # ≤
    '\u2265': r'\geq',       # ≥
    '\u00b7': r'\cdot',      # ·
    '\u00d7': r'\times',     # ×
    '\u00f7': r'\div',       # ÷
    '\u00bd': r'\frac{1}{2}', # ½
    '\u00bc': r'\frac{1}{4}', # ¼
    '\u00be': r'\frac{3}{4}', # ¾
    '\u00b0': r'^\circ',     # °
    '\u2032': r"'",          # ′ (prime)
    '\u2033': r"''",         # ″ (double prime)
    '\u221e': r'\infty',     # ∞
    '\u221a': r'\sqrt{}',    # √
    '\u222b': r'\int',       # ∫
    '\u2202': r'\partial',   # ∂
    '\u2207': r'\nabla',     # ∇
    '\u2192': r'\rightarrow', # →
    '\u2190': r'\leftarrow', # ←
    '\u21d2': r'\Rightarrow', # ⇒
    '\u21d0': r'\Leftarrow', # ⇐
    '\u00b1': r'\pm',        # ±
    '\u2213': r'\mp',        # ∓
    '\u2211': r'\sum',       # ∑
    '\u220f': r'\prod',      # ∏
    # Subscript digits (₀₁₂₃₄₅₆₇₈₉)
    '\u2080': r'_{0}',
    '\u2081': r'_{1}',
    '\u2082': r'_{2}',
    '\u2083': r'_{3}',
    '\u2084': r'_{4}',
    '\u2085': r'_{5}',
    '\u2086': r'_{6}',
    '\u2087': r'_{7}',
    '\u2088': r'_{8}',
    '\u2089': r'_{9}',
    # Superscript digits (⁰¹²³⁴⁵⁶⁷⁸⁹)
    '\u2070': r'^{0}',
    '\u00b9': r'^{1}',
    '\u00b2': r'^{2}',
    '\u00b3': r'^{3}',
    '\u2074': r'^{4}',
    '\u2075': r'^{5}',
    '\u2076': r'^{6}',
    '\u2077': r'^{7}',
    '\u2078': r'^{8}',
    '\u2079': r'^{9}',
}

# Build regex for fast replacement
_UNICODE_PATTERN = re.compile('|'.join(re.escape(ch) for ch in UNICODE_TO_LATEX))


def replace_unicode_math(text: str) -> str:
    """Replace Unicode math characters with LaTeX commands inside math contexts."""
    def replace_match(m):
        ch = m.group(0)
        return UNICODE_TO_LATEX.get(ch, ch)

    # Only replace inside $...$ or $$...$$ blocks (where LaTeX is expected)
    def replace_in_math(m):
        block = m.group(0)
        return _UNICODE_PATTERN.sub(replace_match, block)

    # Process both inline $...$ and block $$...$$
    text = re.sub(r'\$\$[^$]+\$\$', replace_in_math, text)
    text = re.sub(r'(?<!\$)\$[^$\n]+\$(?!\$)', replace_in_math, text)
    return text


def fix_file(md_path: str) -> bool:
    """Fix a single markdown file. Returns True if modified."""
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"  ⚠ 读取失败 {os.path.basename(md_path)}: {e}")
        return False

    original = content

    # 1. Remove backticks around $...$ (double-wrapping)
    # Pattern: `$content$` → $content$
    content = re.sub(r'`(\$[^`]+\$)`', r'\1', content)

    # 2. Convert remaining simple formula backtick blocks to LaTeX
    def convert_code(m):
        code = m.group(1)
        t = code.strip()
        if not t or len(t) > 150:
            return m.group(0)
        if '$' in t:
            return m.group(0)
        # Check if formula-like
        has_ops = bool(re.search(r'[=<>≤≥≠≈±×·÷√^∫∑∏∂]', t))
        has_greek = any('\u0370' <= ch <= '\u03ff' for ch in t)
        has_sub = any('\u2080' <= ch <= '\u2089' for ch in t)
        has_sup = any(c in t for c in '⁰¹²³⁴⁵⁶⁷⁸⁹')
        if has_ops or has_greek or has_sub or has_sup:
            return f"${t}$"
        return m.group(0)

    content = re.sub(r'`([^`]+)`', convert_code, content)

    # 3. Replace Unicode math chars in LaTeX blocks
    content = replace_unicode_math(content)

    # 4. Fix \etac → \eta_c patterns
    content = re.sub(r'\\eta([a-z])(?![_{a-zA-Z}])', r'\\eta_{\1}', content)

    # 5. Fix \sqrt(X) → \sqrt{X}
    content = re.sub(r'\\sqrt\(([^)]*)\)', r'\\sqrt{\1}', content)

    if content != original:
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False


def main():
    # Determine base path
    if len(sys.argv) > 1:
        base = sys.argv[1]
    else:
        base = "/vol2/1000/hdd0/重要文件/obsidian_library/课程录音/通信电子线路"

    print(f"扫描目录: {base}")
    fixed = 0
    total = 0

    for nd in sorted(os.listdir(base)):
        nd_path = os.path.join(base, nd)
        if not os.path.isdir(nd_path):
            continue
        if nd in ("课程录音字幕", "通信电子线路课件") or nd.startswith("未知日期_"):
            continue
        mds = glob.glob(os.path.join(nd_path, "*.md"))
        if not mds:
            continue
        total += 1
        if fix_file(mds[0]):
            fixed += 1
            print(f"  ✅ {nd}")
    print(f"\n扫描 {total} 篇，修复 {fixed} 篇")
    return 0


if __name__ == '__main__':
    sys.exit(main())
