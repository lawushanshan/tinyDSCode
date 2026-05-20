#!/usr/bin/env python3
"""
识别字符串中的所有元音字母（包括大小写），并记录它们的位置和顺序。

功能：
1. 遍历字符串，识别所有元音字母 (a, e, i, o, u, A, E, I, O, U)
2. 记录每个元音字母在原字符串中的索引位置
3. 保持元音字母出现的原始顺序
4. 支持多种输出格式：列表、字典、格式化字符串
5. 支持反转元音列表和反转字符串中的元音
"""


def identify_vowels(s: str) -> list[dict]:
    """
    识别字符串中的所有元音字母，记录它们的位置和顺序。

    遍历字符串中的每个字符，检查是否为元音字母（包括大小写），
    如果是，则记录该字符及其索引位置。

    参数:
        s: 输入字符串

    返回:
        list[dict]: 元音字母信息列表，每个元素包含：
            - 'char': 元音字符本身
            - 'index': 在原字符串中的位置（从 0 开始）
            - 'order': 元音出现的顺序（从 1 开始）

    示例:
        >>> identify_vowels("Hello")
        [{'char': 'e', 'index': 1, 'order': 1},
         {'char': 'o', 'index': 4, 'order': 2}]
    """
    vowels = set('aeiouAEIOU')
    result = []
    order = 0

    for i, ch in enumerate(s):
        if ch in vowels:
            order += 1
            result.append({
                'char': ch,
                'index': i,
                'order': order
            })

    return result


def identify_vowels_grouped(s: str) -> dict[str, list[int]]:
    """
    识别字符串中的所有元音字母，按元音字母分组返回它们的位置。

    参数:
        s: 输入字符串

    返回:
        dict[str, list[int]]: 键为元音字母（保留原始大小写），值为该元音出现的位置列表

    示例:
        >>> identify_vowels_grouped("Hello World")
        {'e': [1], 'o': [4, 7]}
    """
    vowels = set('aeiouAEIOU')
    positions: dict[str, list[int]] = {}

    for i, ch in enumerate(s):
        if ch in vowels:
            positions.setdefault(ch, []).append(i)

    return positions


def identify_vowels_summary(s: str) -> dict:
    """
    生成字符串中元音字母的完整摘要信息。

    参数:
        s: 输入字符串

    返回:
        dict: 包含以下字段的摘要字典：
            - 'total': 元音总数
            - 'unique': 不同元音的种类数
            - 'vowels': 按顺序排列的元音列表（仅字符）
            - 'positions': 按顺序排列的位置列表
            - 'grouped': 按元音分组的详细信息
            - 'first': 第一个元音字符（若无则为 None）
            - 'last': 最后一个元音字符（若无则为 None）
            - 'ratio': 元音占比（0.0 ~ 1.0）
    """
    vowels = set('aeiouAEIOU')
    vowel_chars: list[str] = []
    vowel_positions: list[int] = []
    grouped: dict[str, list[int]] = {}

    for i, ch in enumerate(s):
        if ch in vowels:
            vowel_chars.append(ch)
            vowel_positions.append(i)
            grouped.setdefault(ch, []).append(i)

    total = len(vowel_chars)
    unique = len(grouped)
    length = len(s) if s else 1  # 避免除零

    return {
        'total': total,
        'unique': unique,
        'vowels': vowel_chars,
        'positions': vowel_positions,
        'grouped': grouped,
        'first': vowel_chars[0] if vowel_chars else None,
        'last': vowel_chars[-1] if vowel_chars else None,
        'ratio': round(total / length, 4),
    }


def format_vowel_report(s: str) -> str:
    """
    生成格式化的元音字母分析报告。

    参数:
        s: 输入字符串

    返回:
        str: 格式化的报告文本
    """
    vowels_list = identify_vowels(s)
    summary = identify_vowels_summary(s)

    lines = []
    lines.append("=" * 50)
    lines.append(f"元音字母分析报告")
    lines.append("=" * 50)
    lines.append(f"输入字符串: {s!r}")
    lines.append(f"字符串长度: {len(s)}")
    lines.append(f"元音总数:   {summary['total']}")
    lines.append(f"元音占比:   {summary['ratio'] * 100:.2f}%")
    lines.append(f"不同元音数: {summary['unique']}")
    lines.append("-" * 50)

    if vowels_list:
        lines.append("元音字母出现顺序（按位置排列）:")
        lines.append(f"{'顺序':>5} | {'位置':>5} | {'字符':>5}")
        lines.append("-" * 20)
        for v in vowels_list:
            lines.append(f"{v['order']:>5} | {v['index']:>5} | {v['char']!r:>5}")

        lines.append("-" * 50)
        lines.append("按元音分组的位置:")
        for ch, positions in sorted(summary['grouped'].items()):
            pos_str = ", ".join(str(p) for p in positions)
            lines.append(f"  '{ch}': [{pos_str}]")

        lines.append("-" * 50)
        lines.append(f"第一个元音: {summary['first']!r} (位置 {summary['positions'][0]})")
        lines.append(f"最后一个元音: {summary['last']!r} (位置 {summary['positions'][-1]})")
    else:
        lines.append("字符串中未找到任何元音字母。")

    lines.append("=" * 50)
    return "\n".join(lines)


def reverse_vowels_list(s: str) -> list[dict]:
    """
    识别字符串中的所有元音字母，并返回反转顺序后的列表。

    参数:
        s: 输入字符串

    返回:
        list[dict]: 元音字母信息列表，按出现顺序的反向排列，
                    每个元素包含 'char', 'index', 'order'

    示例:
        >>> reverse_vowels_list("Hello")
        [{'char': 'o', 'index': 4, 'order': 2},
         {'char': 'e', 'index': 1, 'order': 1}]
    """
    vowels_info = identify_vowels(s)
    return list(reversed(vowels_info))


def reverse_vowels_in_string(s: str) -> str:
    """
    反转字符串中的元音字母位置。

    将字符串中所有元音字母的顺序反转，非元音字母保持不变。
    例如: "Hello" -> "Holle" (e 和 o 交换位置)

    参数:
        s: 输入字符串

    返回:
        str: 元音反转后的新字符串

    示例:
        >>> reverse_vowels_in_string("Hello")
        'Holle'
        >>> reverse_vowels_in_string("leetcode")
        'leotcede'
    """
    vowels = set('aeiouAEIOU')
    chars = list(s)

    # 收集所有元音的位置和字符
    positions = []
    vowel_chars = []
    for i, ch in enumerate(chars):
        if ch in vowels:
            positions.append(i)
            vowel_chars.append(ch)

    # 反转元音字符列表
    reversed_vowels = list(reversed(vowel_chars))

    # 将反转后的元音放回原位置
    for pos, ch in zip(positions, reversed_vowels):
        chars[pos] = ch

    return ''.join(chars)


def main():
    """演示 identify_vowels 的各种用法"""
    test_strings = [
        "Hello World! This is a test string.",
        "AEIOUaeiou",
        "Python Programming",
        "Why? (无元音测试)",
        "a",
        "",
        "The quick brown fox jumps over the lazy dog.",
    ]

    print("=" * 60)
    print("识别字符串中的元音字母 — 演示")
    print("=" * 60)

    for s in test_strings:
        print(f"\n{'=' * 60}")
        print(format_vowel_report(s))

    # 演示 reverse_vowels_list
    print(f"\n{'=' * 60}")
    print("演示：reverse_vowels_list() — 反转元音列表")
    print("=" * 60)

    demo_str2 = "Hello World! This is a test string."
    original = identify_vowels(demo_str2)
    reversed_list = reverse_vowels_list(demo_str2)

    print(f"\n原字符串: {demo_str2!r}")
    print(f"\n原始顺序元音列表:")
    for v in original:
        print(f"  顺序 {v['order']:>2}: 位置 {v['index']:>2} -> '{v['char']}'")

    print(f"\n反转后元音列表:")
    for i, v in enumerate(reversed_list, 1):
        print(f"  新顺序 {i:>2}: 位置 {v['index']:>2} -> '{v['char']}' (原顺序 {v['order']})")

    # 演示 reverse_vowels_in_string
    print(f"\n{'=' * 60}")
    print("演示：reverse_vowels_in_string() — 反转字符串中的元音")
    print("=" * 60)

    test_cases = [
        "Hello",
        "leetcode",
        "Hello World! This is a test string.",
        "AEIOU",
        "a.b,c.d",
        "",
    ]

    for s in test_cases:
        result = reverse_vowels_in_string(s)
        print(f"\n  原字符串:  {s!r}")
        print(f"  反转元音:  {result!r}")
        # 显示元音变化
        orig_vowels = [c for c in s if c in set('aeiouAEIOU')]
        new_vowels = [c for c in result if c in set('aeiouAEIOU')]
        if orig_vowels:
            print(f"  元音变化:  {orig_vowels} -> {new_vowels}")

    # 额外演示：使用 identify_vowels 进行元音反转
    print(f"\n{'=' * 60}")
    print("附加演示：基于元音位置信息反转元音")
    print("=" * 60)

    demo_str = "Hello World"
    vowels_info = identify_vowels(demo_str)
    print(f"\n原字符串: {demo_str!r}")
    print(f"元音信息: {vowels_info}")

    # 使用位置信息反转元音
    chars = list(demo_str)
    positions = [v['index'] for v in vowels_info]
    vowel_chars = [v['char'] for v in vowels_info]
    reversed_vowels = list(reversed(vowel_chars))

    for pos, ch in zip(positions, reversed_vowels):
        chars[pos] = ch

    result = ''.join(chars)
    print(f"反转元音: {result!r}")


if __name__ == "__main__":
    main()
