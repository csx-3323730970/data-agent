# Data Agent — 从零实现的数据分析 Agent

一个从零构建的 Agent 框架，不依赖 LangChain 等现成框架。使用 DeepSeek API 作为 LLM，PostgreSQL 作为数据源，通过 Web UI 进行多会话交互式数据分析。

## 功能演示

用户用自然语言描述需求，Agent 自动：
1. 异步执行 SQL 查询（`run_sql`）→ 用 `check_task` 轮询结果
2. 根据数据生成图表（`generate_chart`）→ 柱状图/折线图/饼图
3. 导出分析报告（`export_report`）→ Markdown 格式

支持多窗口 Session 隔离、追问、工具链式调用。

## 项目结构

```
data-agent/
├── src/
│   ├── runtime.py       # 核心 Runtime：Agent Loop、工具调度、异常处理、Context 压缩
│   ├── llm.py           # DeepSeek LLM 客户端（AsyncOpenAI）
│   ├── session.py       # Session 数据模型 + SessionStore 多会话管理
│   ├── server.py        # Flask Web 服务 + REST API
│   ├── config.py        # 配置（全部通过环境变量读取）
│   └── tools/
│       ├── registry.py  # ToolRegistry：工具注册、Schema 导出、统一执行
│       ├── run_sql.py   # 异步 PostgreSQL 查询 + check_task 轮询
│       ├── chart.py     # matplotlib 图表生成（柱/线/饼）
│       └── report.py    # Markdown 报告导出
├── static/
│   └── index.html       # Web UI：多会话切换、聊天天、工具追踪面板
├── data/
│   └── setup.py         # PostgreSQL 数据库初始化（4 表 / 1515 行）
├── docs/
│   └── Agent-Runtime学习笔记.docx  # Runtime 学习笔记 + 面试问答
├── tests/               # 测试用例目录
├── sessions/            # Session JSON 持久化目录
├── reports/             # 图表和报告输出目录
└── requirements.txt
```

## 架构设计

```
用户浏览器（Web UI）
    ↓ HTTP
Flask Server（server.py）
    ↓ Runtime.run(session, message)
┌─────────────────────────────────────┐
│            Agent Runtime            │
│                                     │
│  ┌──────────────────────────────┐  │
│  │        Agent Loop            │  │
│  │  think → act → observe → think │  │
│  └──────────────────────────────┘  │
│         ↓               ↑          │
│  ┌──────────┐   ┌──────────────┐  │
│  │ LLM Client│   │ Tool Registry │  │
│  │(DeepSeek)│   │SQL|Chart|Rpt │  │
│  └──────────┘   └──────────────┘  │
│         ↓               ↑          │
│  ┌──────────────────────────────┐  │
│  │      Context Manager         │  │
│  │  压缩 / 裁剪 / Token 估算    │  │
│  └──────────────────────────────┘  │
└─────────────────────────────────────┘
    ↓ PostgreSQL
```

### 核心模块说明

**Agent Runtime（runtime.py）**
- Agent Loop：`while turns < max_turns` 循环，LLM 返回 tool_calls 时执行工具并回填结果
- 异常处理：LLM 调用自动重试（2次，递增等待）、重复调用检测、未知工具拦截
- Context 压缩：超过 token 阈值时裁剪旧轮次的 tool_result，保留最近 3 轮完整
- 兜底策略：max_turns 强制终止 + 不带 tools 的 LLM 总结

**Session 管理（session.py）**
- 每个 Session 独立持有 messages 列表和 metadata
- SessionStore 管理所有 session 生命周期
- JSON 文件持久化，重启不丢失
- 单用户多窗口场景：窗口 1 和窗口 2 各自拥有独立 session_id，历史互不干扰

**Tool Registry（tools/registry.py）**
- 统一抽象：所有工具按 `{name, description, parameters(JSON Schema), execute}` 注册
- OpenAI function calling 兼容：`get_schemas()` 输出标准 tools 参数格式
- 异步支持：`is_async` 标记区分同步/异步工具

## Memory 的召回时机与放置方式

### 短期记忆（Session Context）
- **放置方式**：完整对话历史保存在 `session.messages` 中，每轮追加 user/assistant/tool 消息
- **召回时机**：每次 Runtime.run() 调用时，全量加载到 messages 列表（以 system prompt 开头）
- **容量限制**：超过 8000 token 时触发 `_maybe_compress()`，裁剪旧轮次的 tool result

### 中期记忆（Context 压缩）
- **放置方式**：旧轮次的 tool_result 截短到 300 字符，保留统计摘要（行数/列名/结果概述）
- **召回时机**：在每轮 Agent Loop 开始前检查 token 估算值
- **压缩策略**：`recent_full_rounds=3` 确保最近 3 轮完整保留，支持追问场景

### 长期记忆（Session 持久化）
- **放置方式**：每个 session 序列化为独立的 JSON 文件（`sessions/{session_id}.json`）
- **召回时机**：SessionStore 初始化时自动加载所有 JSON 文件，用户切换 session 时恢复完整历史
- **存储内容**：全部 messages + session metadata（ID、名称、创建时间、最后活跃时间）

### 设计决策
- 不做全文向量检索的长期 memory。当前场景是"工具调用式 Agent"，用户关注的上下文（数据查询结果、图表引用）都在对话流中
- 压缩使用截短而非 LLM 摘要，因为截短可控、可预测；LLM 摘要可能丢失关键数字或表名
- 工具返回的大数据在源头就做了截断（`_format_result` 限 50 行），context 压缩是第二道防线

## 快速开始

### 环境要求
- Python 3.11+
- PostgreSQL（默认 localhost:5432）
- DeepSeek API Key

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 初始化数据库
确保 PostgreSQL 运行，然后：
```bash
python data/setup.py
```
这会创建 `data_agent` 数据库，包含 products、regions、sales、user_actions 四张表，共 1515 行样例数据。

### 3. 启动服务
```bash
# Linux/Mac
export DEEPSEEK_API_KEY="your-key"
export PG_PASSWORD="your-password"
export PYTHONPATH="."
python src/server.py

# Windows PowerShell
$env:DEEPSEEK_API_KEY = "your-key"
$env:PG_PASSWORD = "your-password"
$env:PYTHONPATH = "."
python src/server.py
```

### 4. 打开浏览器
访问 `http://127.0.0.1:5000`

### 环境变量
| 变量 | 说明 | 必需 |
|------|------|------|
| DEEPSEEK_API_KEY | DeepSeek API 密钥 | 是 |
| PG_PASSWORD | PostgreSQL 密码 | 是 |
| PG_HOST | PostgreSQL 主机 | 否（默认 localhost） |
| PG_PORT | PostgreSQL 端口 | 否（默认 5432） |
| PG_USER | PostgreSQL 用户 | 否（默认 postgres） |
| PG_DATABASE | 数据库名 | 否（默认 data_agent） |
| DEEPSEEK_MODEL | 模型名 | 否（默认 deepseek-v4-flash） |

## 测试用例

### 测试 1：单步查询
```
用户：帮我看看数据库里有哪些表
预期：Agent 调 run_sql("__tables__")，展示 4 张表的结构
```

### 测试 2：多步工具链
```
用户：查一下华东区销售额最高的 5 个产品，画个柱状图
预期：run_sql → chart（依赖 SQL 结果）
```

### 测试 3：多 Session 隔离
```
窗口 1：查销售数据并记待办 → 切换到窗口 2 → 查用户行为数据
切回窗口 1 → 历史完整保留，不受窗口 2 影响
```

### 测试 4：追问
```
用户：查华东区 top 5 产品 → "刚才那个查询，改成只看 6 月的数据"
预期：Agent 理解"刚才那个查询"的上下文，带条件重新查询
```

## 技术栈

- **LLM**: DeepSeek v4 Flash（OpenAI 兼容接口）
- **数据库**: PostgreSQL + asyncpg
- **Web 框架**: Flask
- **图表**: matplotlib
- **前端**: 原生 HTML/CSS/JavaScript
- **异步**: Python asyncio

## 与 LangChain 的对比

| 维度 | 本项目（从零实现） | LangChain |
|------|------|-----------|
| Agent Loop | 约 80 行，完全可控 | AgentExecutor 封装，黑盒 |
| 工具注册 | ToolRegistry 40 行 | BaseTool 抽象 |
| Context 压缩 | 自主实现截短策略 | ConversationSummaryMemory |
| 代码总量 | ~500 行核心逻辑 | 依赖链 >5000 行 |
| 调试透明性 | 每条消息流向可见 | 需要 LangSmith trace |
| 学习价值 | 深入理解 Agent 机制 | 快速原型开发 |
