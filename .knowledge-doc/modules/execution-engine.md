# 执行引擎模块

## 概述

执行引擎模块是系统的核心执行单元，通过 Ralph 循环（观察-分析-决策-执行）完成具体的 Ticket 任务，并内置多种防护机制确保执行稳定。

## 组件

### Worker (执行引擎)
- **位置**: [worker.py](../../src/deepseek_code/worker.py)
- **用途**: 执行 Ticket 任务，通过 Ralph 循环完成工作
- **关键类**:
  - `Worker`: 主执行类
  - `StepDirective`: Supervisor 回调指令

### Ralph 循环
- **四阶段流程**:
  1. **观察 (Observe)**:
     - 从 Harness 获取环境状态（文件列表、快照差异）
     - 从记忆层拉取结构化上下文（近期摘要 + 长期规范）
     - 构建完整消息列表
  2. **分析 (Analyze)**:
     - 调用 LLM 解析当前状态与 Ticket 目标
     - 识别依赖关系和潜在风险
     - 生成思考内容或工具调用
  3. **决策 (Decide)**:
     - 从工具集中选择具体行动
     - 生成工具参数
     - 经过 Harness 的契约校验
     - 内置反思-重试-回退逻辑
  4. **执行 (Execute)**:
     - 将行动指令交给 Harness 层
     - Harness 完成实际的工具调用
     - 异常捕获和状态返回
     - 结果记录到记忆

### 执行流程
- **方法**: `execute_ticket()`
- **参数**:
  - `ticket`: 要执行的 Ticket
  - `model`: 使用的模型
  - `on_step`: Supervisor 回调函数
- **循环控制**:
  - `max_iterations`: 最大循环次数（默认 10）
  - `iteration`: 当前循环计数
- **终止条件**:
  - 满足 Ticket 的 acceptance_criteria
  - 达到 max_loop_iterations
  - Supervisor 中止
  - 连续无进展或重复工具调用

### 防护机制

#### 1. 连续无进展检测
- **触发条件**: 连续 3 次相同内容输出且无工具调用
- **阈值**: `MAX_CONSECUTIVE_NO_PROGRESS = 3`
- **处理**: 终止循环，返回最后内容

#### 2. 重复工具调用检测
- **触发条件**: 连续 3 次完全相同的工具调用
- **阈值**: `MAX_CONSECUTIVE_IDENTICAL_TOOL_CALLS = 3`
- **签名方法**: `_tool_calls_signature()` 序列化工具调用
- **处理**: 终止循环，避免无限重复

#### 3. 进度检查注入
- **触发条件**: 每 5 次循环
- **间隔**: `PROGRESS_CHECK_INTERVAL = 5`
- **注入内容**: 提醒 LLM 评估进展，避免偏离任务
- **处理**: 通过 Supervisor 回调注入系统消息

### Supervisor 回调机制
- **回调时机**:
  - 工具调用前（审批）
  - 工具调用后（汇报）
  - 进度检查（注入提醒）
- **回调函数**: `on_step(step_type, **kwargs)`
- **返回指令**: `StepDirective`
  - `approved`: 是否批准工具调用
  - `inject_message`: 注入消息到记忆
  - `abort`: 是否中止任务

### 工具调用流程
- **步骤**:
  1. LLM 返回工具调用列表
  2. 显示工具调用信息（名称、参数）
  3. 请求 Supervisor 审批（如果提供回调）
  4. 执行工具调用（通过 Harness）
  5. 显示执行结果（成功/失败）
  6. 记录结果到记忆
  7. 执行后汇报（如果提供回调）

### 输出显示
- **使用**: Rich 库美化输出
- **显示内容**:
  - 循环次数和进度
  - 思考内容（截断显示）
  - 工具调用信息
  - 执行结果（成功/失败）
  - 进度检查提醒
  - 完成或终止提示

### 内容截断
- **方法**: `_truncate(text, max_len=200)`
- **用途**: 防止输出过长影响可读性
- **处理**: 超过长度时截断并添加 "..."

## 关键特性

### 1. 自适应执行
- 根据任务复杂度自动调整循环次数
- 通过 LLM 判断任务完成状态
- 动态选择合适的工具

### 2. 安全防护
- 多重防护机制避免无限循环
- Supervisor 审批确保操作安全
- 异常捕获和友好提示

### 3. 可观测性
- 实时显示执行进度
- 详细记录每个步骤
- Rich 美化输出界面

### 4. 可恢复性
- Ticket 状态实时更新
- 执行日志完整记录
- 中断后可从断点恢复

## 使用示例

### 基本执行
```python
worker = Worker(harness=harness, llm_service=llm_service, memory=memory)
result = worker.execute_ticket(ticket, model="deepseek-v4-flash")
```

### 带回调执行
```python
def on_step(step_type, **kwargs):
    if step_type == "before_tool_call":
        tc = kwargs.get("tool_call")
        if tc.name == "run_shell":
            return StepDirective(approved=False, inject_message="Shell 命令被拒绝")
    return StepDirective()

result = worker.execute_ticket(ticket, model="deepseek-v4-flash", on_step=on_step)
```

## 依赖
- `harness`: 安全执行层
- `llm_service`: LLM 调用服务
- `memory`: 记忆管理
- `rich`: 终端 UI