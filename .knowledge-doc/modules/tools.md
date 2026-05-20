# 工具模块

## 概述

工具模块提供了一系列实用的工具函数，用于文件操作、Shell 执行、搜索功能等，并通过工具注册机制支持 OpenAI Function Calling。

## 组件

### Tools (工具实现)
- **位置**: [tools.py](../../src/deepseek_code/tools.py)
- **用途**: 提供具体的工具实现
- **关键类**:
  - `Tools`: 工具实现类（静态方法）
  - `ToolParam`: 工具参数定义
  - `ToolDef`: 工具定义
  - `ToolRegistry`: 工具注册表

### 工具注册机制
- **ToolRegistry**:
  - `register()`: 注册工具
  - `get()`: 获取工具定义
  - `list_tools()`: 列出所有工具
  - `to_openai_schema()`: 转换为 OpenAI Function Calling 格式
- **ToolDef**:
  - `name`: 工具名称
  - `description`: 工具描述
  - `parameters`: 参数列表
  - `handler`: 处理函数
- **ToolParam**:
  - `name`: 参数名称
  - `type`: 参数类型
  - `description`: 参数描述
  - `required`: 是否必需

### 可用工具

#### 1. read_file
- **功能**: 读取文件内容
- **参数**:
  - `path`: 文件路径（必需）
- **返回**: 文件内容字符串
- **异常**: FileNotFoundError（文件不存在）

#### 2. write_file
- **功能**: 写入文件内容，自动创建父目录
- **参数**:
  - `path`: 文件路径（必需）
  - `content`: 要写入的内容（必需）
- **返回**: None
- **特性**: 自动创建父目录

#### 3. list_dir
- **功能**: 列出目录内容
- **参数**:
  - `path`: 目录路径（必需）
- **返回**: 目录项列表（字符串）
- **异常**: FileNotFoundError（路径不存在）

#### 4. run_shell
- **功能**: 执行 shell 命令
- **参数**:
  - `command`: 要执行的命令（必需）
  - `cwd`: 工作目录（可选）
- **返回**: 命令输出或错误信息
- **特性**: 
  - 捕获 stdout 和 stderr
  - 返回执行状态和输出
  - 失败时返回错误信息

#### 5. apply_patch
- **功能**: 应用 unified diff 补丁到文件
- **参数**:
  - `path`: 文件路径（必需）
  - `patch_text`: unified diff 补丁内容（必需）
- **返回**: None
- **特性**: 
  - 解析 diff 格式
  - 精确应用修改
  - 支持多段修改

#### 6. search_files
- **功能**: 按文件名模式搜索文件（glob 风格）
- **参数**:
  - `pattern`: 文件名模式（必需，如 `**/*.py`）
  - `path`: 搜索根目录（可选，默认当前目录）
  - `exclude_patterns`: 排除模式（可选，逗号分隔）
- **返回**: 匹配文件列表
- **特性**: 
  - Glob 模式匹配
  - 默认排除常见目录（`__pycache__`, `.git`, `node_modules` 等）
  - 结果截断（最多 500 个）

#### 7. search_content
- **功能**: 在文件内容中搜索正则匹配（grep 风格）
- **参数**:
  - `pattern`: 正则表达式（必需）
  - `path`: 搜索根目录（可选，默认当前目录）
  - `include`: 只搜索匹配的文件名（可选，如 `*.py`）
  - `exclude`: 排除匹配的文件名（可选，如 `*.log`）
  - `context_lines`: 上下文行数（可选，默认 0）
- **返回**: 匹配内容列表（带行号）
- **特性**: 
  - 正则表达式搜索
  - 支持上下文显示
  - 自动跳过二进制文件
  - 结果截断（最多 100 个匹配）

#### 8. web_search
- **功能**: 联网搜索获取最新信息（使用 Bing 搜索）
- **参数**:
  - `query`: 搜索关键词（必需）
  - `count`: 返回结果数量（可选，默认 5，最大 10）
- **返回**: 搜索结果列表
- **特性**: 
  - 使用 Bing 搜索 API
  - 返回标题、链接、摘要

### 默认排除规则
- **目录**: `__pycache__`, `.git`, `node_modules`, `.venv`, `venv`, `.harness_state`
- **文件**: `*.pyc`
- **二进制文件**: `.pyc`, `.pyo`, `.exe`, `.dll`, `.so`, `.dylib`, `.bin`, `.png`, `.jpg`, `.jpeg`, `.gif`, `.zip`, `.tar`, `.gz`, `.whl`, `.egg`

### 工具创建
- **方法**: `create_default_registry()`
- **用途**: 创建包含所有默认工具的注册表
- **返回**: ToolRegistry 实例

## OpenAI Function Calling 格式
- **转换方法**: `to_openai_schema()`
- **输出格式**:
  ```json
  {
    "type": "function",
    "function": {
      "name": "工具名称",
      "description": "工具描述",
      "parameters": {
        "type": "object",
        "properties": {
          "参数名": {
            "type": "参数类型",
            "description": "参数描述"
          }
        },
        "required": ["必需参数列表"]
      }
    }
  }
  ```

## 安全特性

### 1. 路径验证
- 检查文件/目录是否存在
- 不允许搜索根目录
- 自动处理相对路径

### 2. 结果截断
- 防止输出过长
- 提示用户缩小搜索范围
- 保持可读性

### 3. 异常处理
- FileNotFoundError: 文件不存在
- ValueError: 参数错误
- PermissionError: 权限不足
- re.error: 正则表达式错误

### 4. 编码处理
- UTF-8 编码读写
- 错误忽略模式（搜索时）
- 跨平台兼容

## 使用示例

### 文件操作
```python
content = Tools.read_file("README.md")
Tools.write_file("output.txt", "Hello World")
entries = Tools.list_dir("src")
```

### Shell 执行
```python
result = Tools.run_shell("ls -la", cwd="/path/to/dir")
```

### 搜索功能
```python
files = Tools.search_files("**/*.py", path="src", exclude_patterns="test_*,__pycache__")
matches = Tools.search_content("def.*function", path="src", include="*.py", context_lines=2)
```

### 补丁应用
```python
patch = """
--- a/file.txt
+++ b/file.txt
@@ -1,3 +1,3 @@
 line1
-old line
+new line
 line3
"""
Tools.apply_patch("file.txt", patch)
```

## 依赖
- `pathlib`: 路径处理
- `subprocess`: Shell 执行
- `re`: 正则表达式
- `fnmatch`: 文件名匹配
- `pydantic`: 数据验证