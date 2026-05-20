# 项目架构

## 概述

**tinyDSCode** (DeepSeek Code CLI) 是一个 Claude Code 风格的 AI 编码助手，采用 **Supervisor + Worker** 的极简架构，深度融合 **Ralph 循环**（观察-分析-决策-执行）与 **Harness Engineer**（安全装具工程）思想。

## 核心设计理念

1. **安全第一**：所有文件/命令操作必须经过 Harness 层，提供沙箱、Git 原子提交和权限分级
2. **可解释性**：Ralph 循环的每个阶段与 Ticket 状态均在 UI 中可视化，审计日志完整记录
3. **弹性与恢复**：内置状态机与 Ticket 生命周期管理，支持任务中断后从精确断点恢复
4. **渐进式演进**：单 Worker 设计为后续分化为 Planner、Coder、Reviewer 等专业智能体预留接口
5. **长程记忆管理**：通过三层记忆架构自动压缩上下文，有效延长有效工作窗口

## 系统架构图

```
用户层
  └─ CLI / REPL 入口
      └─ Supervisor Agent (任务调度 + 状态机)
          ├─ Ticket 系统 (任务队列)
          ├─ 状态持久化 (.harness_state/)
          └─ Worker (执行引擎)
              ├─ Ralph 循环 (观察→分析→决策→执行)
              ├─ Memory Manager (三层记忆)
              └─ Harness (安全执行层)
                  ├─ 权限守护
                  ├─ 审计日志
                  └─ 工具层
                      ├─ 文件操作
                      ├─ Shell 执行
                      └─ 搜索功能
```

## 核心组件

### 1. Supervisor Agent (任务调度器)
- **位置**: [supervisor.py](../../src/deepseek_code/supervisor.py)
- **职责**: 接收用户输入，生成高层计划，以 Ticket 形式分派子任务给 Worker
- **状态机**: Idle → Planning → Dispatching → WaitingWorker → Reviewing → Complete/Failed
- **关键特性**:
  - 自动任务拆分（通过 LLM）
  - Ticket 生命周期管理
  - 状态持久化和恢复

### 2. Worker (执行引擎)
- **位置**: [worker.py](../../src/deepseek_code/worker.py)
- **职责**: 执行具体的 Ticket 任务，通过 Ralph 循环完成工作
- **Ralph 循环四阶段**:
  1. **观察 (Observe)**: 从 Harness 获取环境状态
  2. **分析 (Analyze)**: 调用 LLM 解析当前状态与目标
  3. **决策 (Decide)**: 选择工具并生成参数
  4. **执行 (Execute)**: 通过 Harness 层执行操作
- **防护机制**:
  - 连续无进展检测
  - 重复工具调用检测
  - 进度检查注入

### 3. Harness (安全执行层)
- **位置**: [harness.py](../../src/deepseek_code/harness.py)
- **职责**: 提供安全的工具执行环境
- **关键特性**:
  - 权限请求机制（交互式/自动模式）
  - 审计日志记录
  - 工具调用封装

### 4. Memory Manager (记忆管理)
- **位置**: [memory.py](../../src/deepseek_code/memory.py)
- **职责**: 管理对话历史和上下文压缩
- **三层记忆架构**:
  - **工作记忆**: 当前 Ralph 循环的完整对话列表
  - **近期记忆**: 结构化摘要 + 滑动窗口
  - **长期记忆**: 项目规范文件 (DEEPSEEK.md)
- **Token 预算驱动**: 自动压缩以控制上下文长度

### 5. Tools (工具层)
- **位置**: [tools.py](../../src/deepseek_code/tools.py)
- **可用工具**:
  - `read_file`: 读取文件内容
  - `write_file`: 写入文件（自动创建目录）
  - `list_dir`: 列出目录内容
  - `run_shell`: 执行 shell 命令
  - `apply_patch`: 应用 unified diff 补丁
  - `search_files`: 按文件名模式搜索
  - `search_content`: 在文件内容中搜索
  - `web_search`: 联网搜索

### 6. LLM Service (LLM 服务)
- **位置**: [llm_service.py](../../src/deepseek_code/llm_service.py)
- **职责**: 封装 LLM API 调用
- **特性**:
  - OpenAI 兼容模式
  - Function Calling 支持
  - 模拟响应模式（无 API Key 时）

### 7. Persistence (持久化)
- **位置**: [persistence.py](../../src/deepseek_code/persistence.py)
- **存储位置**: `.harness_state/` 目录
- **持久化内容**:
  - `tickets.json`: 所有 Ticket 列表及状态
  - `audit_log.json`: 操作审计日志（最近 1000 条）
  - `supervisor.json`: Supervisor 状态机状态

## 数据流

```
用户输入
  ↓
CLI 解析
  ↓
Supervisor 创建 Ticket
  ↓
Supervisor 规划子任务
  ↓
Worker 执行 Ticket (Ralph 循环)
  ├─ 观察环境 (通过 Harness)
  ├─ 分析状态 (调用 LLM)
  ├─ 决策行动 (选择工具)
  └─ 执行操作 (通过 Harness)
      ↓
工具执行结果
  ↓
Worker 返回结果
  ↓
Supervisor 汇总并完成 Ticket
  ↓
输出给用户
```

## 技术栈

| 组件 | 选型 |
|------|------|
| 语言 | Python 3.11+ |
| 异步 | asyncio, anyio |
| LLM 客户端 | openai (兼容 DeepSeek API) |
| 终端 UI | rich |
| 状态机 | 自研轻量级 |
| 数据验证 | pydantic |
| 打包 | pipx, uv |

## 后续演进路线

- **v0.1 - MVP**: Ticket 系统 + 双层记忆压缩
- **v0.2 - 专业智能体分化**: Ticket 类型标签，路由到 Planner/Coder/Reviewer
- **v0.3 - 长期记忆与生态**: 向量数据库实现长期记忆检索，MCP 支持
- **v0.4+**: 多 Worker 并行执行 Ticket，完整 Memory Bank 可视化，IDE 集成