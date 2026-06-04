"""Generic post-processing: verify and fix knowledge maps in all notes.

Checks:
1. $$...$$ enclosure is compact (no blank line between $$ and content)
2. \\begin{array} / \\end{array} counts are balanced
3. No stray code fences wrapping math blocks

Also applies fixes automatically when possible:
- Removes code fences wrapping $$...$$ blocks
- Fixes missing \\end{array} in unbalanced blocks

Usage:
    python3 scripts/verify_knowledge_map.py <file.md|directory>
"""

import os, re, sys


def check_and_fix_file(path: str, fix: bool = False) -> list[str]:
    """Check a single markdown file for knowledge map issues.
    If fix=True, attempt to fix issues in-place."""
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    issues = []
    modified = False

    # Check 1: Remove code fences wrapping $$...$$
    for m in re.finditer(r'```(?:latex)?\s*\n\$\$', content):
        line_num = content[:m.start()].count('\n') + 1
        issues.append(f"  L{line_num}: 代码块围栏包裹 $$（Obsidian不渲染）")
        if fix:
            # Remove the ```latex or ``` before $$
            content = content[:m.start()] + content[m.start():].lstrip('`').lstrip('latex').lstrip('\n')
            modified = True

    # Check 2: Find all $$...$$ blocks and check array balance
    for m in re.finditer(r'\$\$(.*?)\$\$', content, re.DOTALL):
        block = m.group(1)
        start = m.start()

        opens = block.count(r'\begin{array}')
        closes = block.count(r'\end{array}')

        if opens != closes:
            line_num = content[:start].count('\n') + 1
            issues.append(f"  L{line_num}: begin={{}}:{opens}, end={{}}:{closes} ✗ UNBALANCED")
            if fix and opens > closes:
                # Append missing \\end{array}$$ 
                insert_pos = m.end() - 2  # before closing $$
                content = content[:insert_pos] + r'\end{array}' + content[insert_pos:]
                modified = True

        # Check compact format
        if 'begin{array}' in block:
            inner = block.strip()
            if inner.startswith('\n'):
                line_num = content[:start].count('\n') + 1
                issues.append(f"  L{line_num}: 非紧凑格式（$$与\\\\begin{array}之间有换行）")

        # Check for stray code fence inside math block
        if '```' in block:
            line_num = content[:start].count('\n') + 1
            issues.append(f"  L{line_num}: $$内含有代码块围栏 ```")

    if modified:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

    return issues


def main():
    targets = sys.argv[1:]
    fix_mode = '--fix' in targets
    if fix_mode:
        targets.remove('--fix')

    if not targets:
        print("用法: python3 verify_knowledge_map.py [--fix] <file.md|directory>")
        sys.exit(1)

    total_issues = 0
    fixed_count = 0

    for target in targets:
        if os.path.isdir(target):
            files = [os.path.join(target, f) for f in sorted(os.listdir(target))
                     if f.endswith('.md')]
        else:
            files = [target]

        for path in files:
            if not os.path.isfile(path):
                continue
            issues = check_and_fix_file(path, fix=fix_mode)
            if issues:
                print(f"📄 {os.path.basename(path)}:")
                for issue in issues:
                    print(issue)
                total_issues += len(issues)
                fixed_count += 1
            elif fix_mode and not issues:
                pass  # No issues found, skip

    if total_issues == 0:
        print("✅ 所有文件通过检查")
    else:
        status = "已修复" if fix_mode else "待修复"
        print(f"\n⚠️ 共 {total_issues} 个问题，{status} ({fixed_count} 个文件)")


if __name__ == '__main__':
    main()
