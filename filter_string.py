def filter_string(s: str) -> str:
    """
    提取字符串中的所有字母数字字符，并转换为小写。

    参数:
        s: 输入字符串

    返回:
        只包含字母数字字符的小写字符串
    """
    return ''.join(ch.lower() for ch in s if ch.isalnum())


if __name__ == '__main__':
    # 测试用例
    test_cases = [
        ("Hello World!", "helloworld"),
        ("Python 3.9", "python39"),
        ("ABC123!@#", "abc123"),
        (" 空格 和 制表符\t", "空格和制表符"),
        ("", ""),
        ("!@#$%", ""),
        ("AaBbCc123", "aabbcc123"),
    ]

    all_pass = True
    for input_str, expected in test_cases:
        result = filter_string(input_str)
        if result == expected:
            print(f'PASS: filter_string({input_str!r}) = {result!r}')
        else:
            print(f'FAIL: filter_string({input_str!r}) = {result!r} (期望: {expected!r})')
            all_pass = False

    print(f'\n所有测试 {"通过" if all_pass else "失败"}!')
