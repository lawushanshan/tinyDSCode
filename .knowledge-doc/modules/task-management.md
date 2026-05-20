# 任务管理模块

## 概述

任务管理模块是系统的核心调度系统，负责接收用户请求、拆分任务、管理 Ticket 生命周期、协调 Worker 执行，并提供状态持久化和恢复能力。

## 组件

### Supervisor Agent
- **位置**: [supervisor.py](../../src/deepseek_code/supervisor.py)
- **用途**: 任务调度器，管理整个任务执行流程
- **关键类**:
  - `SupervisorState`: 状态机枚举
  - `Ticket`: 任务工单数据结构
  - `Supervisor`: 主调度器类

### 状态机
- **状态定义**:
  - `IDLE`: 空闲状态
  - `PLANNING`: 正在规划任务
  - `DISPATCHING`: 正在分派任务
  - `WAITING_WORKER`: 等待 Worker 执行
  - `REVIEWING`: 正在审查结果
  - `COMPLETE`: 任务完成
  - `FAILED`: 任务失败
- **状态转换规则**:
  ```
  IDLE → PLANNING
  PLANNING → DISPATCHING / FAILED
  DISPATCHING → WAITING_WORKER
  WAITING_WORKER → REVIEWING / DISPATCHING / FAILED
  REVIEWING → COMPLETE / DISPATCHING / FAILED
  COMPLETE → IDLE
  FAILED → IDLE
  ```
- **转换验证**: `_transition()` 方法验证转换合法性

### Ticket 系统
- **数据结构**:
  ```python
  class Ticket(BaseModel):
      ticket_id: str              # 唯一标识，如 T-001
      parent_ticket_id: Optional[str]  # 父 Ticket ID（支持子任务）
      status: Literal["pending", "running", "blocked", "done", "failed"]
      description: str            # 任务描述
      result: Optional[str]       # 执行结果
      acceptance_criteria: Optional[str]  # 完成标准
      max_loop_iterations: int = 10  # 最大循环次数
      created_at: datetime        # 创建时间
      updated_at: datetime        # 更新时间
      log: list[str]              # 执行日志
  ```
- **生命周期**:
  1. **pending**: 已创建，等待分配
  2. **running**: Worker 正在执行
  3. **blocked**: 遇到需外部解决的问题
  4. **done**: 满足验收标准，关闭
  5. **failed**: 超过最大循环次数或不可恢复错误

### 任务规划
- **方法**: `plan_task()`
- **流程**:
  1. 构建规划提示词（要求 LLM 返回 JSON 数组）
  2. 调用 LLM 进行任务拆分
  3. 解析 JSON 响应，提取子任务描述
- **输出格式**: `[{"description": "子任务描述"}]`

### 任务执行流程
- **方法**: `handle_prompt()`
- **完整流程**:
  1. 转换状态到 PLANNING
  2. 创建父 Ticket
  3. 规划子任务（如果需要）
  4. 创建子 Ticket（关联父 Ticket）
  5. 转换状态到 DISPATCHING
  6. 启动 Ticket（状态变为 running）
  7. 转换状态到 WAITING_WORKER
  8. Worker 执行 Ticket
  9. 转换状态到 REVIEWING
  10. 汇总结果，完成父 Ticket
  11. 保存审计日志
  12. 转换状态到 COMPLETE
  13. 最终转换到 IDLE

### Worker 回调机制
- **回调类型**:
  - `before_tool_call`: 工具调用前审批
  - `after_tool_call`: 工具调用后汇报
  - `progress_check`: 进度检查注入
- **返回指令**: `StepDirective`
  - `approved`: 是否批准操作
  - `inject_message`: 注入消息到记忆
  - `abort`: 是否中止任务

### REPL 模式
- **方法**: `start_repl()`
- **功能**:
  - 循环读取用户输入
  - 处理内置命令（`:help`, `:tickets`, `:status`, `:new`）
  - 执行任务并显示结果
  - 异常捕获和友好提示

### 状态持久化
- **方法**:
  - `_persist_state()`: 持久化 Supervisor 状态
  - `_persist_tickets()`: 持久化 Ticket 列表
  - `_load_state()`: 加载历史状态
- **存储位置**: `.harness_state/`
  - `supervisor.json`: 状态机状态
  - `tickets.json`: Ticket 列表

## 关键特性

### 1. 可追溯性
- 每个 Ticket 有唯一 ID
- 日志和审计可精确关联
- 完整的执行历史记录

### 2. 可恢复性
- 状态持久化到文件
- 中断后可从断点恢复
- Ticket 状态可重新调度

### 3. 可扩展性
- 支持子任务层级
- 为多 Worker 并行预留接口
- Ticket 类型标签（未来）

## 使用示例

### 创建和执行 Ticket
```python
supervisor = Supervisor(state_root=str(Path.cwd()))
ticket = supervisor.create_ticket("读取 README.md")
supervisor.start_ticket(ticket)
result = supervisor.worker.execute_ticket(ticket)
supervisor.complete_ticket(ticket, result)
```

### REPL 交互
```python
supervisor.start_repl()
# 用户输入: :tickets
# 输出: T-001 [done] - 读取 README.md
```

## 依赖
- `worker`: Worker 执行引擎
- `harness`: 安全执行层
- `llm_service`: LLM 调用服务
- `memory`: 记忆管理
- `tools`: 工具注册
- `persistence`: 状态持久化