#!/usr/bin/env python3
"""
将输入字符串转换为字符列表以便修改
"""

def string_to_charlist(s: str) -> list:
    """将字符串转换为字符列表"""
    return list(s)


def main():
    # 示例用法
    input_str = "Hello World"
    char_list = string_to_charlist(input_str)
    print(f"输入字符串: '{input_str}'")
    print(f"字符列表: {char_list}")
    print(f"列表长度: {len(char_list)}")
    
    # 演示修改能力
    print("\n--- 修改演示 ---")
    # 修改第一个字符
    char_list[0] = 'h'
    print(f"修改后: {''.join(char_list)}")


if __name__ == "__main__":
    main()
