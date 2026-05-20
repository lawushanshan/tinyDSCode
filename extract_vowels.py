def extract_vowels(s: str) -> list[dict]:
    """
    提取字符串中的所有元音字母（包括大小写），并记录它们的位置。

    元音字母：a, e, i, o, u（大小写均包含）

    返回一个列表，每个元素是一个字典，包含：
        - 'char': 元音字符
        - 'index': 在原字符串中的位置（从 0 开始）

    Args:
        s: 输入字符串

    Returns:
        list[dict]: 元音字母信息列表
    """
    vowels = set('aeiouAEIOU')
    result = []
    for i, ch in enumerate(s):
        if ch in vowels:
            result.append({'char': ch, 'index': i})
    return result


def extract_vowels_with_positions(s: str) -> dict:
    """
    提取字符串中的所有元音字母，按元音分组返回它们的位置。

    返回一个字典，键为元音字母（小写），值为该元音出现的位置列表。

    Args:
        s: 输入字符串

    Returns:
        dict: 元音字母 -> 位置列表
    """
    vowels = set('aeiouAEIOU')
    positions = {}
    for i, ch in enumerate(s):
        if ch in vowels:
            key = ch.lower()
            positions.setdefault(key, []).append(i)
    return positions


def reverse_vowels_list(vowels: list[dict]) -> list[dict]:
    """
    反转提取的元音字母列表顺序。

    Args:
        vowels: extract_vowels 返回的元音列表

    Returns:
        list[dict]: 反转后的元音列表
    """
    return list(reversed(vowels))


def reverse_vowels_in_string(s: str) -> str:
    """
    反转字符串中的元音字母。

    遍历原字符串，将非元音字符保持不变，按顺序用反转后的元音字母
    替换原位置的元音字母，生成新字符串。

    Args:
        s: 输入字符串

    Returns:
        str: 元音反转后的新字符串
    """
    vowels_set = set('aeiouAEIOU')
    # 提取所有元音字符
    vowels_chars = [ch for ch in s if ch in vowels_set]
    # 反转元音列表
    reversed_vowels = list(reversed(vowels_chars))
    # 遍历原字符串，用反转后的元音替换
    result_chars = []
    rev_idx = 0
    for ch in s:
        if ch in vowels_set:
            result_chars.append(reversed_vowels[rev_idx])
            rev_idx += 1
        else:
            result_chars.append(ch)
    return ''.join(result_chars)


if __name__ == '__main__':
    # 测试
    test_str = "Hello World! This is a test string."
    print(f"输入字符串: {test_str!r}")
    print()

    result1 = extract_vowels(test_str)
    print("=== extract_vowels 结果（原始顺序） ===")
    for item in result1:
        print(f"  位置 {item['index']:2d}: '{item['char']}'")
    print(f"共找到 {len(result1)} 个元音字母")
    print()

    # 反转元音列表
    reversed_result = reverse_vowels_list(result1)
    print("=== extract_vowels 结果（反转后） ===")
    for item in reversed_result:
        print(f"  位置 {item['index']:2d}: '{item['char']}'")
    print(f"共找到 {len(reversed_result)} 个元音字母")
    print()

    result2 = extract_vowels_with_positions(test_str)
    print("=== extract_vowels_with_positions 结果 ===")
    for vowel, positions in sorted(result2.items()):
        print(f"  '{vowel}': 位置 {positions}")
    print()

    # 测试元音反转
    reversed_str = reverse_vowels_in_string(test_str)
    print("=== reverse_vowels_in_string 结果 ===")
    print(f"  原字符串: {test_str!r}")
    print(f"  反转后:   {reversed_str!r}")
    print()
    print("  说明：原字符串中的元音字母被反转顺序替换，非元音字母保持不变。")
