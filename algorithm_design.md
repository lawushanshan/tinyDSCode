# 最长无重复字符子串 — 滑动窗口算法设计

## 1. 问题定义

**题目**：给定一个字符串 `s`，找出其中不含有重复字符的**最长子串**的长度。

**示例**：
| 输入 | 输出 | 解释 |
|------|------|------|
| `"abcabcbb"` | 3 | 最长子串是 `"abc"`，长度为 3 |
| `"bbbbb"` | 1 | 最长子串是 `"b"`，长度为 1 |
| `"pwwkew"` | 3 | 最长子串是 `"wke"`，长度为 3 |
| `""` | 0 | 空字符串 |
| `" "` | 1 | 空格字符 |

## 2. 核心思路：滑动窗口（Sliding Window）

### 2.1 为什么用滑动窗口？

子串是原字符串中**连续**的一段，天然适合用**窗口**来框选。通过移动窗口的左右边界，可以在 O(n) 时间内遍历所有可能的无重复子串。

### 2.2 数据结构选择

| 数据结构 | 作用 | 时间复杂度 |
|---------|------|-----------|
| **哈希集合** `set` | 记录当前窗口内的字符，O(1) 判断重复 | O(1) 查/插/删 |
| **双指针** `left`, `right` | 定义窗口范围 `[left, right]` | O(1) 移动 |

### 2.3 为什么用哈希集合而不是哈希表？

- **哈希集合**：只关心"字符是否在窗口内"，不关心位置
- **哈希表**：记录字符位置，可以一次性跳转 left，但本题用集合+逐步移动 left 更直观

> **进阶**：如果追求极致性能，可以用哈希表记录字符位置，遇到重复时 left 直接跳到 `char_map[ch] + 1`，但本题用集合已足够。

## 3. 算法流程

```
输入: 字符串 s
输出: 最长无重复子串的长度

1. 初始化：
   - left = 0          ← 窗口左边界
   - max_len = 0       ← 记录最大长度
   - char_set = set()  ← 记录窗口内的字符

2. 遍历字符串（right 从 0 到 n-1）：
   a. 如果 s[right] 不在 char_set 中：
      - 将 s[right] 加入 char_set
      - 更新 max_len = max(max_len, right - left + 1)
      - right++（继续扩展窗口）
   
   b. 如果 s[right] 在 char_set 中（重复）：
      - 从 char_set 中移除 s[left]
      - left++（收缩窗口）
      - 重复此步骤直到 s[right] 不再重复

3. 返回 max_len
```

### 可视化示例：`"abcabcbb"`

```
初始: left=0, right=0, set={}, max_len=0

Step 1: right=0, ch='a'
  set 无 'a' → 加入 → set={'a'}, max_len=1
  [a] b c a b c b b

Step 2: right=1, ch='b'
  set 无 'b' → 加入 → set={'a','b'}, max_len=2
  [a b] c a b c b b

Step 3: right=2, ch='c'
  set 无 'c' → 加入 → set={'a','b','c'}, max_len=3
  [a b c] a b c b b

Step 4: right=3, ch='a'
  set 有 'a' → 移除 s[left]='a', left=1 → set={'b','c'}
  set 无 'a' → 加入 → set={'b','c','a'}, max_len=3
  a [b c a] b c b b

Step 5: right=4, ch='b'
  set 有 'b' → 移除 s[left]='b', left=2 → set={'c','a'}
  set 无 'b' → 加入 → set={'c','a','b'}, max_len=3
  a b [c a b] c b b

... 以此类推，最终 max_len=3
```

## 4. 复杂度分析

| 维度 | 复杂度 | 说明 |
|------|--------|------|
| 时间复杂度 | **O(n)** | 每个字符最多被 left 和 right 各访问一次 |
| 空间复杂度 | **O(min(m, n))** | m 为字符集大小（如 ASCII 128），n 为字符串长度 |

### 为什么是 O(n) 而不是 O(n²)？

虽然内层有 while 循环收缩窗口，但每个字符最多被 left 指针移除一次，所以总操作次数是 **2n**（每个字符被 right 加入一次，被 left 移除一次），即 O(n)。

## 5. 边界情况

| 场景 | 处理方式 |
|------|---------|
| 空字符串 `""` | left=0, right=-1，循环不执行，返回 0 |
| 单字符 `"a"` | 加入 set，max_len=1 |
| 全重复 `"aaaa"` | 每次 right 移动后 left 立即跟进，max_len=1 |
| 无重复 `"abc"` | 窗口持续扩大，max_len=3 |
| 含空格 `"a b"` | 空格作为普通字符处理 |
| Unicode 字符 | Python set 支持任意可哈希类型 |

## 6. 代码实现

```python
def length_of_longest_substring(s: str) -> int:
    """
    使用滑动窗口 + 哈希集合找出最长无重复字符子串的长度。
    
    参数:
        s: 输入字符串
    返回:
        最长无重复字符子串的长度
    """
    char_set = set()   # 记录当前窗口内的字符
    left = 0           # 窗口左边界
    max_len = 0        # 最大长度
    
    for right, ch in enumerate(s):
        # 如果字符重复，收缩窗口直到不再重复
        while ch in char_set:
            char_set.remove(s[left])
            left += 1
        
        # 将当前字符加入窗口
        char_set.add(ch)
        
        # 更新最大长度
        max_len = max(max_len, right - left + 1)
    
    return max_len
```

## 7. 测试验证

```python
# 测试用例
assert length_of_longest_substring("abcabcbb") == 3
assert length_of_longest_substring("bbbbb") == 1
assert length_of_longest_substring("pwwkew") == 3
assert length_of_longest_substring("") == 0
assert length_of_longest_substring(" ") == 1
assert length_of_longest_substring("au") == 2
assert length_of_longest_substring("dvdf") == 3
assert length_of_longest_substring("abba") == 2
```

## 8. 优化方案：哈希表版（直接跳转）

如果使用哈希表记录字符位置，遇到重复时 left 可以直接跳转，减少 while 循环次数：

```python
def length_of_longest_substring_optimized(s: str) -> int:
    """
    优化版：使用哈希表记录字符位置，遇到重复时直接跳转 left。
    """
    char_map = {}    # 字符 → 最近出现位置
    left = 0
    max_len = 0
    
    for right, ch in enumerate(s):
        # 如果字符在窗口内重复，left 直接跳到上次出现位置的下一个
        if ch in char_map and char_map[ch] >= left:
            left = char_map[ch] + 1
        
        # 更新字符位置
        char_map[ch] = right
        
        # 更新最大长度
        max_len = max(max_len, right - left + 1)
    
    return max_len
```

**两种方案对比**：

| 方案 | 优点 | 缺点 |
|-----|------|------|
| 哈希集合版 | 直观易懂，逻辑清晰 | left 逐步移动，最坏情况 O(2n) |
| 哈希表版 | left 直接跳转，严格 O(n) | 需要处理位置边界条件 |

## 9. 总结

- **核心思想**：滑动窗口 + 哈希集合
- **关键操作**：遇到重复字符时收缩窗口左边界
- **时间复杂度**：O(n)，线性时间
- **空间复杂度**：O(min(m, n))，取决于字符集大小
- **适用场景**：所有需要处理"连续子串/子数组"且涉及"不重复"条件的问题
