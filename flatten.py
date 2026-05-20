"""
展平嵌套列表工具函数
支持任意嵌套深度的列表展平为一维列表
"""

from collections.abc import Iterable
from typing import Any, List


def flatten_recursive(nested_list: Any) -> List[Any]:
    """
    递归方式展平嵌套列表

    参数:
        nested_list: 任意嵌套的列表或元素

    返回:
        一维列表

    示例:
        >>> flatten_recursive([1, [2, [3, 4], 5], 6])
        [1, 2, 3, 4, 5, 6]
        >>> flatten_recursive([])
        []
        >>> flatten_recursive([1, 2, 3])
        [1, 2, 3]
    """
    result = []
    for item in nested_list:
        if isinstance(item, list):
            result.extend(flatten_recursive(item))
        else:
            result.append(item)
    return result


def flatten_iterative(nested_list: Any) -> List[Any]:
    """
    迭代方式展平嵌套列表（使用栈，避免递归深度限制）

    参数:
        nested_list: 任意嵌套的列表或元素

    返回:
        一维列表

    示例:
        >>> flatten_iterative([1, [2, [3, 4], 5], 6])
        [1, 2, 3, 4, 5, 6]
        >>> flatten_iterative([])
        []
        >>> flatten_iterative([1, 2, 3])
        [1, 2, 3]
    """
    result = []
    stack = [nested_list]

    while stack:
        current = stack.pop()
        if isinstance(current, list):
            # 逆序压栈，保持原始顺序
            for item in reversed(current):
                stack.append(item)
        else:
            result.append(current)

    return result


def flatten_generator(nested_list: Any):
    """
    生成器方式展平嵌套列表（惰性求值，节省内存）

    参数:
        nested_list: 任意嵌套的列表或元素

    返回:
        生成器，逐个 yield 展平后的元素

    示例:
        >>> list(flatten_generator([1, [2, [3, 4], 5], 6]))
        [1, 2, 3, 4, 5, 6]
    """
    for item in nested_list:
        if isinstance(item, list):
            yield from flatten_generator(item)
        else:
            yield item


def flatten(nested_list: Any, method: str = "recursive") -> List[Any]:
    """
    统一接口：展平嵌套列表

    参数:
        nested_list: 任意嵌套的列表或元素
        method: 方法选择，可选 "recursive"、"iterative"、"generator"

    返回:
        一维列表
    """
    if method == "recursive":
        return flatten_recursive(nested_list)
    elif method == "iterative":
        return flatten_iterative(nested_list)
    elif method == "generator":
        return list(flatten_generator(nested_list))
    else:
        raise ValueError(f"未知方法: {method}，可选 'recursive', 'iterative', 'generator'")


# ========== 测试 ==========

def test_flatten():
    """测试用例"""
    test_cases = [
        # (输入, 期望输出)
        ([1, [2, [3, 4], 5], 6], [1, 2, 3, 4, 5, 6]),  # 示例输入
        ([], []),                                          # 空列表
        ([1, 2, 3], [1, 2, 3]),                            # 单层列表
        ([[1, 2], [3, 4], [5, 6]], [1, 2, 3, 4, 5, 6]),  # 两层嵌套
        ([1, [2, [3, [4, [5]]]]], [1, 2, 3, 4, 5]),       # 深层嵌套（5层）
        ([[[[[1], 2], 3], 4], 5], [1, 2, 3, 4, 5]),       # 反向深层嵌套
        ([0, [1, [2, [3]]], [[4], 5]], [0, 1, 2, 3, 4, 5]), # 混合嵌套
        ([None, [True, [False]]], [None, True, False]),    # 混合类型
        (["a", ["b", ["c"]]], ["a", "b", "c"]),            # 字符串类型
    ]

    all_pass = True
    for method in ["recursive", "iterative", "generator"]:
        print(f"\n===== 测试方法: {method} =====")
        for i, (input_list, expected) in enumerate(test_cases, 1):
            try:
                result = flatten(input_list, method=method)
                assert result == expected, f"用例 {i} 失败: {input_list} => {result}, 期望 {expected}"
                print(f"  [PASS] 用例 {i}: {input_list} => {result}")
            except Exception as e:
                print(f"  [FAIL] 用例 {i}: {e}")
                all_pass = False

    if all_pass:
        print("\n===== 全部测试通过! =====")
    else:
        print("\n===== 存在失败的测试! =====")


if __name__ == "__main__":
    test_flatten()

    # 演示用法
    print("\n===== 使用示例 =====")
    data = [1, [2, [3, 4], 5], [6, [7, [8, 9]]]]
    print(f"原始嵌套列表: {data}")
    print(f"递归展平:      {flatten(data, 'recursive')}")
    print(f"迭代展平:      {flatten(data, 'iterative')}")
    print(f"生成器展平:    {flatten(data, 'generator')}")
