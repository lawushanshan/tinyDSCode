 DeepSeek Code Harness v0.1 最终架构文档（增强版）


flowchart TB
    subgraph User["👤 用户层"]
        CLI["CLI / REPL 入口"]
    end

    subgraph Supervisor["🧠 Supervisor Agent"]
        StateMachine["状态机"]
        TaskQueue["任务队列 (Ticket)"]
        TicketPool["Ticket 池<br/>(pending/running/blocked/done)"]
        Persistence["状态持久化<br/>(.harness_state/)"]
    end

    subgraph Worker["🔧 通用 Worker (唯一执行体)"]
        subgraph RalphLoop["🔄 Ralph 循环引擎"]
            direction LR
            O["观察<br/>Observe<br/>(环境/上下文/安全状态)"] --> A["分析<br/>Analyze<br/>(意图/依赖/风险)"]
            A --> D["决策<br/>Decide<br/>(选择行动/生成参数)"]
            D --> E["执行<br/>Execute<br/>(通过Harness层)"]
            E --> O
        end
        ContextCompactor["上下文自适应压缩"]
    end

    subgraph Memory["💾 三层记忆架构"]
        direction TB
        Working["工作记忆<br/>(当前循环完整历史)"]
        Recent["近期记忆<br/>(结构化摘要+滑动窗口)"]
        LongTerm["长期记忆<br/>(DEEPSEEK.md / 向量数据库)"]
        Compressor["记忆压缩器<br/>(Token预算驱动, 异步)"]
        Working -->|压缩触发| Compressor
        Compressor -->|生成结构化摘要| Recent
        Recent -->|持久化/语义索引| LongTerm
    end

    subgraph Harness["⚙️ Harness Engineer 安全执行层"]
        direction TB
        Sandbox["沙箱 & 快照 (Docker/文件副本)"]
        GitGuard["Git 原子提交 & 回滚"]
        Contract["契约 & 权限守护"]
        Stubs["环境桩 (Mock)"]
        AuditLog["审计日志"]
    end

    subgraph Tools["🛠️ 工具层"]
        FS["文件系统"]
        Shell["Shell 执行 (受控)"]
        Grep["代码搜索"]
    end

    subgraph LLM["☁️ LLM 推理"]
        DeepSeek["DeepSeek API<br/>(OpenAI 兼容模式)"]
    end

    subgraph UI["🖥️ 终端界面"]
        RichPanel["Rich 动态面板<br/>(状态、计划、日志、Ticket看板)"]
    end

    CLI --> Supervisor
    Supervisor --> Worker
    Worker --> RalphLoop
    RalphLoop -- "工具调用请求" --> Harness
    Harness --> Tools
    Tools -- "执行结果/异常" --> Harness
    Harness -- "安全状态/结构化结果" --> RalphLoop
    RalphLoop -. "读写上下文" .-> Working
    Working -. "溢出触发" .-> Compressor
    Compressor -. "注入摘要" .-> Recent
    RalphLoop -. "获取压缩后上下文" .-> Recent
    RalphLoop -. "读取项目规范" .-> LongTerm
    RalphLoop -. "LLM 请求" .-> DeepSeek
    DeepSeek -. "响应" .-> RalphLoop
    StateMachine -.-> Persistence
    TaskQueue -.-> TicketPool
    RichPanel -. 实时状态 .-> Supervisor
    RichPanel -. 实时状态 .-> Worker
    RichPanel -. 实时状态 .-> Harness
    RichPanel -. 记忆状态 .-> Memory


1. 概述
DeepSeek Code Harness 是一个基于 Python 的命令行 AI 编码助手，采用 Supervisor + 单 Worker 的极简架构，深度融合 Ralph 循环（观察-分析-决策-执行）与 Harness Engineer（安全装具工程）思想。本版本新增 Ticket 驱动的任务管理 和 三层记忆压缩机制，确保任务可追踪、可恢复，并在长会话中保持高密度上下文。

2. 设计目标
安全第一：所有文件/命令操作必须经过 Harness 层，提供沙箱、Git 原子提交和权限分级。

可解释性：Ralph 循环的每个阶段与 Ticket 状态均在 UI 中可视化，审计日志完整记录。

弹性与恢复：内置状态机与 Ticket 生命周期管理，支持任务中断后从精确断点恢复。

渐进式演进：单 Worker 设计为后续分化为 Planner、Coder、Reviewer 等专业智能体预留接口。

长程记忆管理：通过三层记忆架构自动压缩上下文，有效延长有效工作窗口。

3. 核心组件
3.1 Supervisor Agent（含 Ticket 系统）
职责：接收用户输入，生成高层计划，并以 Ticket（任务工单） 的形式将子任务分派给 Worker，监控全局状态。

状态机：定义了 Idle → Planning → Dispatching → WaitingWorker → Reviewing → Complete/Failed 的状态转换，每个状态变更持久化到 .harness_state/supervisor.json。

Ticket 数据结构：

python
class Ticket(BaseModel):
    ticket_id: str
    parent_ticket_id: Optional[str]  # 支持子任务
    status: Literal["pending", "running", "blocked", "done", "failed"]
    description: str
    context: dict  # 所需文件路径、相关代码片段等
    acceptance_criteria: Optional[str]  # 完成标准
    max_loop_iterations: int = 10
    created_at: datetime
    assigned_worker: Optional[str]
Ticket 生命周期管理：

pending：已创建，等待分配。

running：Worker 正在执行。

blocked：遇到需外部解决的问题（如权限不足）。

done：满足验收标准，关闭。

failed：超过最大循环次数或不可恢复错误。

优势：

可追溯：每个子任务有唯一 ID，日志和审计可精确关联。

可恢复：Supervisor 可根据 Ticket 状态重新调度或人工干预。

可并行（未来）：多 Worker 时可形成任务池。

3.2 通用 Worker（内嵌 Ralph 循环）
Worker 是所有具体工作的执行者，其核心是 Ralph 循环。Worker 拉取一个 Ticket，并将其目标作为循环的终止条件。

循环四阶段：

观察：从 Harness 获取环境状态（文件列表、快照差异、上次命令输出），从记忆层拉取结构化上下文（近期摘要 + 长期规范）。

分析：调用 LLM 解析当前状态与 Ticket 目标，识别依赖关系和潜在风险。

决策：从工具集中选择具体行动，生成参数，并经过 Harness 的契约校验。同时内置 反思-重试-回退 逻辑：连续无效决策会强制返回分析阶段。

执行：将行动指令交给 Harness 层，由 Harness 完成实际的工具调用、异常捕获和状态返回。

终止条件：满足 Ticket 的 acceptance_criteria（由 LLM 判断）或达到 max_loop_iterations。

Ticket 关联：整个循环过程以 Ticket ID 为纽带，所有日志、审计、记忆条目都关联此 ID。

3.3 三层记忆架构与压缩器
用于解决长上下文带来的 Token 爆炸和遗忘问题，实现记忆的高信息密度管理。

工作记忆：当前 Ralph 循环的完整对话列表（内存），保持操作的精确性。

近期记忆：由压缩器生成的结构化摘要，配合滑动窗口机制，作为上下文缓冲区。

触发机制：Token 预算驱动。当上下文用量达到模型最大窗口的 80% 时，异步触发压缩。

压缩方法：双阶段“蒸馏”，要求 LLM 输出结构化 JSON 摘要，保留关键决策、文件变更、错误、下一步行动等，而非自然语言描述。

掩码优化：对早期冗余的工具输出用占位符替换，进一步节省 Token。

长期记忆：跨会话的持久化知识。包括：

项目规范文件 DEEPSEEK.md（可自动更新）。

后续版本将引入向量数据库，实现语义检索和经验复用。

上下文组装：每个循环周期的输入为：[System Prompt] + [项目规范] + [结构化摘要] + [滑动窗口内最近K轮对话] + [当前Ticket]。

3.4 Harness Engineer 安全执行层
（保持不变，细节略）

沙箱与快照、Git 原子提交、契约与权限、环境桩、审计日志。所有操作必须经由此层，审计日志关联 Ticket ID 和循环步骤。

3.5 工具层
read_file、write_file、edit_file、run_shell、grep、glob。

3.6 终端界面
基于 rich 的实时面板，新增 Ticket 看板：显示各 Ticket 的状态、进度、关联日志。支持中断热键暂停/检查/修改 Ticket。

4. 典型工作流程（融合 Ticket 与记忆压缩）
用户输入 deepseek-code "修复 auth.ts 的登录超时bug"。

Supervisor 创建父 Ticket T-001，并规划出 4 个子 Ticket：

T-001-1：定位 auth.ts

T-001-2：分析超时逻辑

T-001-3：生成修复

T-001-4：运行测试验证

Supervisor 将 T-001-1 分派给 Worker，状态变为 running。

Worker 启动 Ralph 循环，循环输入包含记忆层提供的结构化上下文。

随着循环进行，工作记忆不断增长。当接近 Token 上限时，压缩器在后台生成结构化摘要，存入近期记忆。

T-001-1 完成（状态 done），Worker 回报，Supervisor 推进到 T-001-2。

全部子 Ticket 完成后，Supervisor 汇总结果，UI 展示修复摘要，Git 历史记录所有变更。

5. 技术栈（不变）
组件	选型
语言	Python 3.11+
异步	asyncio, anyio
LLM 客户端	openai (兼容 DeepSeek API)
终端 UI	rich
状态机	自研轻量级或 transitions
数据验证	pydantic
向量存储 (v0.3+)	Chroma / LanceDB
打包	pipx, uv
6. 后续演进路线（更新）
v0.1 – MVP：在原有基础上，立即集成 Ticket 系统和双层记忆压缩（工作+近期）。

v0.2 – 专业智能体分化：Ticket 增加类型标签，用于路由到 Planner/Coder/Reviewer。

v0.3 – 长期记忆与生态：引入向量数据库实现长期记忆检索，MCP 支持。

v0.4+：多 Worker 并行执行 Ticket，完整 Memory Bank 可视化，IDE 集成。