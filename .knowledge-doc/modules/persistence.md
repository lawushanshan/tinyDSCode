# 持久化模块

## 概述

持久化模块负责状态持久化，包括 Ticket 存储、审计日志、Supervisor 状态等，确保任务可恢复和可追溯。

## 组件

### StateManager
- **位置**: [persistence.py](../../src/deepseek_code/persistence.py)
- **用途**: 状态持久化管理
- **关键类**: `StateManager`

### 存储位置
- **目录**: `.harness_state/`
- **创建**: 自动创建（如果不存在）
- **位置**: 当前工作目录下
- **文件**:
  - `tickets.json`: 所有 Ticket 列表及状态
  - `audit_log.json`: 操作审计日志（最近 1000 条）
  - `supervisor.json`: Supervisor 状态机状态

### 持久化内容

#### 1. Tickets
- **方法**:
  - `save_tickets()`: 保存 Ticket 列表
  - `load_tickets()`: 加载 Ticket 列表
- **数据**: Ticket 的完整信息（ID、状态、描述、结果、日志等）
- **格式**: JSON 数组
- **用途**: 
  - 任务恢复
  - 状态查看
  - 历史追溯

#### 2. 审计日志
- **方法**:
  - `save_audit_log()`: 保存审计日志
  - `load_audit_log()`: 加载审计日志
- **数据**: 操作记录（工具调用、权限请求、错误等）
- **格式**: JSON 数组
- **限制**: 最近 1000 条（避免无限增长）
- **用途**: 
  - 操作追溯
  - 安全审计
  - 问题诊断

#### 3. Supervisor 状态
- **方法**:
  - `save_supervisor_state()`: 保存 Supervisor 状态
  - `load_supervisor_state()`: 加载 Supervisor 状态
- **数据**: 状态机当前状态、更新时间
- **格式**: JSON 对象
- **用途**: 
  - 状态恢复
  - 断点续传
  - 状态验证

### JSON 处理
- **写入**: `_write_json()`
- **读取**: `_read_json()`
- **编码**: UTF-8
- **格式**: 
  - `ensure_ascii=False`: 支持中文
  - `indent=2`: 格式化输出
  - `default=str`: 自定义序列化（datetime 等）

### 审计日志限制
- **最大条目**: 1000
- **策略**: 保留最近 N 条
- **处理**: `trimmed = audit_log[-max_entries:]`
- **目的**: 防止文件过大，保持性能

### 状态恢复
- **流程**:
  1. Supervisor 初始化时调用 `_load_state()`
  2. 加载历史 Ticket 列表
  3. 加载 Supervisor 状态
  4. 恢复到上次中断点
- **条件**: `load_state=True`（默认）

### 文件结构示例
```
.harness_state/
├── tickets.json
├── audit_log.json
└── supervisor.json
```

### tickets.json 示例
```json
[
  {
    "ticket_id": "T-001",
    "parent_ticket_id": null,
    "status": "done",
    "description": "读取 README.md",
    "result": "文件内容...",
    "acceptance_criteria": null,
    "max_loop_iterations": 10,
    "created_at": "2026-05-20T14:30:00Z",
    "updated_at": "2026-05-20T14:35:00Z",
    "log": [
      "创建 Ticket: T-001",
      "Ticket 开始执行",
      "工具调用: read_file(...)",
      "工具结果 [成功]: ...",
      "Ticket 完成"
    ]
  }
]
```

### audit_log.json 示例
```json
[
  {
    "action": "tool_call",
    "tool": "read_file",
    "arguments": {"path": "README.md"}
  },
  {
    "action": "tool_result",
    "tool": "read_file",
    "result": "文件内容..."
  },
  {
    "action": "permission_request",
    "operation": "shell",
    "detail": "ls -la",
    "approval": true
  }
]
```

### supervisor.json 示例
```json
{
  "state": "idle",
  "updated_at": "2026-05-20T14:35:00Z"
}
```

## 关键特性

### 1. 自动创建
- 目录不存在时自动创建
- 文件不存在时返回空数据
- 无需手动初始化

### 2. 数据限制
- 审计日志限制 1000 条
- 防止文件过大
- 保持性能

### 3. 格式友好
- UTF-8 编码
- 格式化输出
- 支持中文
- 可读性强

### 4. 自定义序列化
- datetime 自动转换
- 支持复杂对象
- 灵活扩展

### 5. 状态恢复
- 自动加载历史状态
- 支持断点续传
- 任务可恢复

## 使用示例

### 基本使用
```python
state_manager = StateManager(root=Path.cwd())
state_manager.save_tickets([ticket.model_dump()])
tickets = state_manager.load_tickets()
```

### 审计日志
```python
audit_log = [
    {"action": "tool_call", "tool": "read_file", "arguments": {"path": "README.md"}}
]
state_manager.save_audit_log(audit_log)
log = state_manager.load_audit_log()
```

### Supervisor 状态
```python
state_data = {"state": "planning", "updated_at": datetime.now(timezone.utc).isoformat()}
state_manager.save_supervisor_state(state_data)
loaded = state_manager.load_supervisor_state()
```

### 自定义根目录
```python
state_manager = StateManager(root="/path/to/project")
```

## 依赖
- `pathlib`: 路径处理
- `json`: JSON 处理
- `typing`: 类型提示