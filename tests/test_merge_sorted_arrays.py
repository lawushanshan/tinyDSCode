"""测试 merge_sorted_arrays 模块。"""

import pytest
from deepseek_code.merge_sorted_arrays import merge_sorted_arrays


class TestMergeSortedArrays:
    """合并两个已排序数组的测试。"""

    def test_both_non_empty(self) -> None:
        """正常场景：两个非空数组。"""
        assert merge_sorted_arrays([1, 3, 5], [2, 4, 6]) == [1, 2, 3, 4, 5, 6]

    def test_with_duplicates(self) -> None:
        """包含重复元素。"""
        assert merge_sorted_arrays([1, 1, 2], [1, 3]) == [1, 1, 1, 2, 3]

    def test_first_empty(self) -> None:
        """边界条件：第一个数组为空。"""
        assert merge_sorted_arrays([], [1, 2]) == [1, 2]

    def test_second_empty(self) -> None:
        """边界条件：第二个数组为空。"""
        assert merge_sorted_arrays([1, 2], []) == [1, 2]

    def test_both_empty(self) -> None:
        """边界条件：两个数组都为空。"""
        assert merge_sorted_arrays([], []) == []

    def test_single_element_each(self) -> None:
        """边界条件：各只有一个元素。"""
        assert merge_sorted_arrays([1], [2]) == [1, 2]
        assert merge_sorted_arrays([2], [1]) == [1, 2]

    def test_all_elements_from_first(self) -> None:
        """所有元素来自第一个数组（第二个数组元素都更大）。"""
        assert merge_sorted_arrays([1, 2, 3], [4, 5, 6]) == [1, 2, 3, 4, 5, 6]

    def test_all_elements_from_second(self) -> None:
        """所有元素来自第二个数组（第一个数组元素都更大）。"""
        assert merge_sorted_arrays([4, 5, 6], [1, 2, 3]) == [1, 2, 3, 4, 5, 6]

    def test_negative_numbers(self) -> None:
        """包含负数。"""
        assert merge_sorted_arrays([-3, -1, 0], [-2, 1]) == [-3, -2, -1, 0, 1]

    def test_large_numbers(self) -> None:
        """包含大整数。"""
        assert merge_sorted_arrays([10**9, 10**9 + 5], [10**9 + 2]) == [
            10**9,
            10**9 + 2,
            10**9 + 5,
        ]

    def test_uneven_lengths(self) -> None:
        """两个数组长度差异较大。"""
        assert merge_sorted_arrays([1], [2, 3, 4, 5]) == [1, 2, 3, 4, 5]
        assert merge_sorted_arrays([1, 2, 3, 4], [5]) == [1, 2, 3, 4, 5]

    def test_identical_elements(self) -> None:
        """所有元素相同。"""
        assert merge_sorted_arrays([1, 1, 1], [1, 1]) == [1, 1, 1, 1, 1]

    def test_does_not_mutate_input(self) -> None:
        """不应修改输入列表。"""
        arr1 = [1, 3, 5]
        arr2 = [2, 4, 6]
        original1 = arr1.copy()
        original2 = arr2.copy()
        merge_sorted_arrays(arr1, arr2)
        assert arr1 == original1
        assert arr2 == original2

    def test_returns_new_list(self) -> None:
        """应返回新列表而非引用。"""
        arr1 = [1, 2]
        arr2 = [3, 4]
        result = merge_sorted_arrays(arr1, arr2)
        assert result is not arr1
        assert result is not arr2
