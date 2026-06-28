# AI Prompt 与问题解决记录

## 一、System Prompt 设计

### 版本 1（初版）

```
你是一个数据分析助手 Agent。你可以使用工具来帮助用户完成数据分析任务。

规则：
1. 当用户提出数据分析需求时，先用 run_sql 查询数据，用 generate_chart 画图，用 export_report 导出报告
2. run_sql 是异步工具，调用后会返回 task_id，需要用 check_task 轮询结果
3. 工具返回的数据可能很大，你需要在回复中做归纳总结，不要直接复制原始数据
4. 追问时，基于前文的查询结果继续分析，不需要重复已经做过的查询
5. 用中文回复用户
```

**问题**：Agent 输出大量 Markdown 格式符号（`**`、`|`、`##`、emoji），中文段落不整洁。

### 版本 2（当前版本）

```
你是一个数据分析助手 Agent。使用工具帮用户完成数据分析任务。

规则：
1. 数据分析时，先用 run_sql 查数据，再用 generate_chart 画图，最后用 export_report 导出报告
2. run_sql 是异步工具，返回 task_id 后用 check_task 轮询结果
3. 工具返回的数据可能很大，做归纳总结，不要直接复制原始数据
4. 追问时基于前文结果继续分析，不重复查询
5. 全程用中文

回复格式要求：
- 禁止使用 markdown 语法：不要用 ** 加粗、不要用 | 画表格、不要用 ## 标题、不要用 ``` 代码块
- 禁止使用 emoji
- 使用自然段落和平实的文字描述。列举时用换行加短横线即可
- 语气简洁、专业，像一位数据分析师在汇报
```

**改进**：明确禁止 Markdown 和 emoji，指定了期望的文字风格。

---

## 二、问题解决记录

### 问题 1：Async 后台任务不执行，LLM 反复轮询 check_task 但永远拿不到结果

**现象**：LLM 调了 run_sql（异步），然后连续 9 次调 check_task，每次都返回 pending。达到 max_turns 被强制终止。

**根因**：LLM 客户端 `chat()` 方法是同步的（`openai.OpenAI`），在 `async def run()` 中调用时阻塞了事件循环。`run_sql` 的 `asyncio.create_task` 创建的后台任务虽然有 `asyncio.sleep(5)` 延迟，但在同步阻塞期间永远得不到执行机会。

**解决**：将 `llm.py` 从 `OpenAI` 改为 `AsyncOpenAI`，`chat()` 改为 `async def`。Runtime 中所有调用都加 `await`。这样 LLM API 调用期间事件循环继续运行，后台任务可以正常推进。

**涉及文件**：`src/llm.py`、`src/runtime.py`

---

### 问题 2：PostgreSQL 日期类型插入失败

**现象**：`data/setup.py` 执行 `INSERT INTO sales ... VALUES ($1, $2, $3, '2026-03-08')` 时报错 `'str' object has no attribute 'toordinal'`。

**根因**：asyncpg 驱动对 DATE 列要求 Python 的 `datetime.date` 对象，不接受字符串。

**解决**：将日期字符串 `f"2026-{month:02d}-{day:02d}"` 改为 `date(2026, month, day)` 对象。

**涉及文件**：`data/setup.py`

---

### 问题 3：check_task 轮询时 LLM 陷入死循环

**现象**：LLM 调了 run_sql 后连续调 check_task（相同参数），即使结果已经返回后仍继续调。

**根因**：LLM 没有意识到第 5 次 check_task 已经返回了 done 状态，或者因为对话历史太长导致它忽略了早先的工具结果。同工具同参数的连续调用也说明 LLM 进入了"不断尝试"的模式。

**解决**：在 Runtime 中加入重复调用检测——记录上一轮的工具名和参数（fingerprint），如果连续两轮完全相同，注入系统消息强制 LLM 基于已有信息作答。`SAME_TOOL_REPEAT_LIMIT = 3`。

**涉及文件**：`src/runtime.py`（`last_tool_fingerprint` 检测逻辑）

---

### 问题 4：Server 启动时报 ModuleNotFoundError: No module named 'src'

**现象**：`python src/server.py` 报错找不到 `src` 模块。

**根因**：项目根目录不在 Python 的模块搜索路径中。

**解决**：设置环境变量 `$env:PYTHONPATH = "."`（PowerShell）或 `export PYTHONPATH="."`（Bash）。

---

### 问题 5：LLM 输出格式混乱（Markdown + Emoji）

**现象**：Agent 自我介绍时输出包含 `**`、`|` 表格、`##` 标题、`📊🧠👋` 等 emoji，在 Web UI 中显示不整洁。

**根因**：System Prompt 未约束输出格式，DeepSeek 默认倾向使用 Markdown。

**解决**：在 System Prompt 中加入明确的格式禁令（见上文版本 2），禁止 Markdown 语法和 emoji，指定期望的文本风格。

**涉及文件**：`src/llm.py`（SYSTEM_PROMPT）

---

### 问题 6：Config 中硬编码凭据被 Git 追踪

**现象**：`src/config.py` 中 API Key 和数据库密码以默认值形式存在，会被提交到 GitHub。

**根因**：初期为了方便测试将凭据写为了环境变量的默认值（`os.environ.get("KEY", "hardcoded-value")`）。

**解决**：将敏感配置改为强制环境变量（`os.environ["KEY"]`，无默认值），添加 `.gitignore` 和 `.env.example` 模板文件。

**涉及文件**：`src/config.py`、`.gitignore`、`.env.example`

---

### 问题 7：前端会话切换失效（null 引用崩溃）

**现象**：点击左侧会话列表中的另一个会话，chat 窗口内容不切换，仍显示当前会话。

**根因**：`selectSession()` 函数中 `document.getElementById('empty-state').style.display = 'none'` 在 `empty-state` 元素已被 DOM 移除后抛出 `TypeError: Cannot read properties of null`。函数提前终止，`loadHistory(sid)` 从未执行。`empty-state` 元素在首次加载消息后即被 `appendMessage()` 移除。

**解决**：加 null 检查 `if (emptyState) emptyState.style.display = 'none'`，`loadHistory()` 加 `await` 确保异步完成后再返回。

**涉及文件**：`static/index.html`

---

### 问题 8：重复调用检测时机错误 → DeepSeek 400 错误

**现象**：LLM 连续轮询 check_task 后，服务端日志显示 `Error code: 400 - insufficient tool messages following tool_calls message`。

**根因**：重复调用检测在工具执行**之前**触发。检测到连续重复后，代码直接调 LLM 做强制总结，但 messages 列表中最后一条 assistant 消息包含 `tool_calls` 却没有对应的 `tool` 结果消息。DeepSeek API 的 message 格式校验拒绝了这个不完整的请求。

**解决**：重构 Agent Loop 中的检测顺序——先执行工具、添加 tool 结果到 messages、再检测重复。这样触发强制终止时，messages 末尾的 tool_calls 已经有对应的 tool 结果，格式始终合法。同时加强错误处理，强制总结的 LLM 调用失败时返回兜底文本。

**涉及文件**：`src/runtime.py`

---

### 问题 9：SAME_TOOL_REPEAT_LIMIT 定义但未实际使用

**现象**：`check_task` 第二次连续调用就被强制终止，但代码中明明写了 `SAME_TOOL_REPEAT_LIMIT = 3`。

**根因**：limit 常量定义了，但检测代码只用 `if fingerprint == last_tool_fingerprint` 判断——首次重复就触发，没有累加计数逻辑。对 `check_task` 这种需要多次轮询的工具过于激进。

**解决**：新增 `same_tool_streak` 计数器。每次检测到相同指纹且结果仍为 pending 时 streak+1，仅当 `streak >= SAME_TOOL_REPEAT_LIMIT` 时才触发终止。limit 从 3 放宽到 5，给异步任务更充裕的完成窗口。

**涉及文件**：`src/runtime.py`

---

### 问题 10：done 结果被误判为重复导致立即终止（修复引入的新 bug）

**现象**：修复问题 8 后，check_task 终于返回 done，但 Agent 立即被终止，数据到了却来不及用。

**根因**：修复 8 时额外加了 "非 pending 的重复调用立即终止" 逻辑（`same_tool_streak = SAME_TOOL_REPEAT_LIMIT`）。当 check_task 从 pending 变为 done —— fingerprint 相同但 result status 改变 —— 被判定为"非 pending 重复"，streak 直接到上限，瞬间终止循环。

**解决**：回退为简洁逻辑——仅连续 pending 累积 streak；done、error、不同工具调用均重置 streak 为 0。done 状态的重复交给 max_turns 兜底。

**涉及文件**：`src/runtime.py`

---

### 问题 11：多步工具链因回合预算不足提前终止

**现象**：用户问"查华东 top5 商品并画柱状图"，Agent 只返回了数据库表结构描述，未执行实际查询。

**根因**：`MAX_TURNS=10` 且 `ASYNC_DELAY_SECONDS=5`。每个异步 SQL 需约 6 轮（1 提交 + 5 轮询等待 5s 延迟）。LLM 先调用 `__tables__` 查看表结构耗去 7 轮，剩 3 轮给实际查询——第二个异步任务来不及等到 done 就被 max_turns 截断。

**解决**：`MAX_TURNS` 从 10 上调至 20，`ASYNC_DELAY_SECONDS` 从 5s 下调至 2s。每个异步 SQL 周期降为约 4 轮，20 轮足以支持多步工具链（__tables__ + 实际查询 + 画图 + 报告）。

**涉及文件**：`src/config.py`

---

### 问题 12：Python import 别名导致 asyncpg pool 清理失效（Event loop is closed）

**现象**：重启 Server 后第一个请求成功，第二个请求报 `Event loop is closed`，第三个又正常，交替出现。

**根因**：`from src.tools.run_sql import _pool as _sql_pool` 在 import 时将 `_sql_pool` 绑定到当时的**对象** `None`。之后 `_get_pool()` 通过 `global _pool` 将模块级变量重绑定为新 Pool 实例，但 server.py 中的 `_sql_pool` 仍然指向 `None`。finally 块中 `if _sql_pool is not None` 永远为 False，pool 清理从未执行。

请求 1 的 pool 关闭后残留。请求 2 时 `_get_pool()` 发现 `_pool` 不是 None（是请求 1 的残留 pool），直接返回，但该 pool 的连接绑定到请求 1 的已关闭事件循环 → "Event loop is closed"。请求 2 失败后 pool 恰好在异常中被意外清理，请求 3 又能创建新 pool 正常工作。

**解决**：改为 `import src.tools.run_sql as sql_mod`，在 finally 中用 `sql_mod._pool` 动态访问模块级变量的**当前值**，而非 import 时的快照。

**涉及文件**：`src/server.py`

---

### 问题 13：环境变量手动设置繁琐

**现象**：每次启动 Server 需在终端手动设置 `DEEPSEEK_API_KEY` 等环境变量，容易遗忘导致 401 认证错误。

**根因**：项目未集成 .env 文件自动加载机制。

**解决**：在 `config.py` 顶部添加 `load_dotenv()`，创建 `.env` 文件存储凭据，`python-dotenv` 加入 `requirements.txt`。启动时自动读取，无需手动 export。

**涉及文件**：`src/config.py`、`.env`、`requirements.txt`

---

## 三、Prompt 迭代心得

1. **System Prompt 要约束"不要什么"，而不只是"要什么"**。初版只说了"用中文回复"，没说不允许 Markdown。加上"禁止使用 markdown 语法"后效果立竿见影。

2. **异步工具的提示词需要精确描述交互模式**。"调用后会返回 task_id，需要用 check_task 轮询结果"——这句话让 LLM 理解了异步工具的"提交 → 轮询 → 获取结果"三段式流程。

3. **工具的 description 和 parameters 描述直接影响 LLM 的调用准确率**。`run_sql` 的 description 中包含"传 `__tables__` 可查看所有表结构"这个特例，让 LLM 在"看看数据库有什么"时不至于写 `SELECT * FROM information_schema.tables`。

4. **temperature=0.1 对工具调用场景很重要**。低温度减少了 LLM 的"创造性"，让它更倾向于严格按 tools schema 调用，减少了幻觉工具名和参数格式错误。

5. **工具间的依赖关系要在 description 中说明**。`generate_chart` 的 description 中写明 data_json 的格式（`{"labels": [...], "values": [...]}`），LLM 就能正确地从 run_sql 的结果中提取数据喂给画图工具。
