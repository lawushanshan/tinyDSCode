# CLI 模块

## 概述

CLI 模块是用户与 DeepSeek Code 交互的主要入口，提供命令行解析、REPL 模式和任务执行功能。

## 组件

### CLI 入口
- **位置**: [cli.py](../../src/deepseek_code/cli.py)
- **用途**: 解析命令行参数，初始化 Supervisor，执行用户任务
- **关键函数**:
  - `parse_args()`: 解析命令行参数
  - `main()`: 主入口函数
  - `parse_args()`: 支持 run、repl、models、eval 四个子命令

### 命令类型

#### 1. `deepseek-code run <任务描述>`
- **用途**: 单次执行模式
- **流程**:
  1. Supervisor 创建父 Ticket
  2. 自动拆分为子 Ticket
  3. Worker 逐个执行
  4. 汇总结果输出
- **参数**:
  - `prompt`: 任务描述（必需）
  - `--model`: 模型预设名称或原始模型字符串

#### 2. `deepseek-code repl`
- **用途**: 启动交互式 REPL 会话
- **特性**:
  - 多轮对话支持
  - 内置命令系统
  - Ticket 状态查看
- **可用命令**:
  - `:help`: 显示帮助信息
  - `:tickets`: 查看当前会话的所有 Ticket 及状态
  - `:status`: 查看当前正在执行的 Ticket 详情
  - `:new <描述>`: 创建并执行新 Ticket
  - `exit` / `quit`: 退出会话

#### 3. `deepseek-code models`
- **用途**: 列出可用的模型预设
- **输出**: 表格形式显示预设名称、模型、API Base

#### 4. `deepseek-code eval`
- **用途**: 运行 L1 代码生成评估基准
- **参数**:
  - `--model`: 模型预设
  - `--tasks-dir`: 自定义任务目录
  - `--task-ids`: 指定 task_id 列表
  - `--categories`: 按类别筛选
  - `--difficulties`: 按难度筛选
  - `--output-dir`: 报告输出目录
  - `--timeout`: 测试执行超时秒数
  - `--stop-on-error`: 首次失败即停

### 配置管理
- **位置**: [config.py](../../src/deepseek_code/config.py)
- **用途**: 加载和管理模型配置
- **关键函数**:
  - `load_config()`: 加载配置文件
  - `resolve_model()`: 解析模型参数
  - `list_models()`: 列出可用模型
- **配置文件**: `.deepseek-code.json`
- **配置结构**:
  ```json
  {
    "models": [
      {
        "name": "预设名称",
        "model": "模型字符串",
        "api_base": "API地址",
        "api_key_env": "环境变量名"
      }
    ],
    "default": "默认预设名称"
  }
  ```

## 使用示例

### 单次执行
```powershell
deepseek-code run "读取 README.md 并总结"
deepseek-code run "创建一个 hello.py 文件"
deepseek-code run "列出 src 目录下所有 Python 文件"
```

### REPL 模式
```powershell
deepseek-code repl
DeepSeek> 读取 src/deepseek_code/cli.py 的内容
DeepSeek> :tickets
DeepSeek> :status
DeepSeek> :new 修复 auth.ts
DeepSeek> exit
```

### 模型选择
```powershell
deepseek-code run "任务" --model deepseek-v4-pro
deepseek-code models
```

## 环境变量

```powershell
# 必需（二选一）
setx DEEPSEEK_API_KEY "your_deepseek_key"
setx OPENAI_API_KEY "your_openai_key"

# 可选
setx DEEPSEEK_API_BASE "https://api.deepseek.com"
```

## 依赖
- `argparse`: 命令行解析
- `rich`: 终端 UI
- `supervisor`: 任务调度
- `config`: 配置管理