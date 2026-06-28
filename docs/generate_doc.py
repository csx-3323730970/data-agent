"""Generate Agent Runtime 学习笔记 .docx"""
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
import os

doc = Document()

for section in doc.sections:
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)

style = doc.styles['Normal']
style.font.name = 'Microsoft YaHei'
style.font.size = Pt(11)
style.paragraph_format.space_after = Pt(6)
style.paragraph_format.line_spacing = 1.5
style.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

for level in range(1, 4):
    h = doc.styles[f'Heading {level}']
    h.font.name = 'Microsoft YaHei'
    h.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
    h.font.color.rgb = RGBColor(0x1A, 0x1A, 0x2E)

def add_para(text, bold=False, size=None):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    if size:
        run.font.size = Pt(size)
    run.font.name = 'Microsoft YaHei'
    run.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

def add_bullet(text):
    p = doc.add_paragraph(text, style='List Bullet')

def add_table(headers, rows):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = 'Light Grid Accent 1'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = h
        for p in cell.paragraphs:
            for r in p.runs:
                r.bold = True
                r.font.size = Pt(10)
                r.font.name = 'Microsoft YaHei'
                r.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = table.rows[ri + 1].cells[ci]
            cell.text = str(val)
    doc.add_paragraph()

# ═══ TITLE ═══
doc.add_paragraph()
doc.add_paragraph()
title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = title.add_run('Agent Runtime\n学习笔记与面试问答')
run.bold = True
run.font.size = Pt(28)
run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x2E)
run.font.name = 'Microsoft YaHei'
run.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = sub.add_run('以 data-agent 项目为教材，从零构建 Agent 框架')
run.font.size = Pt(14)
run.font.color.rgb = RGBColor(0x88, 0x88, 0x88)
run.font.name = 'Microsoft YaHei'
run.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

date_p = doc.add_paragraph()
date_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = date_p.add_run('2026年6月28日')
run.font.size = Pt(11)
run.font.color.rgb = RGBColor(0xAA, 0xAA, 0xAA)
run.font.name = 'Microsoft YaHei'
run.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
doc.add_page_break()

# ═══ CHAPTER 1 ═══
doc.add_heading('第一章：Agent Runtime 学习笔记', level=1)

doc.add_heading('1.1 Runtime 在系统中的位置', level=2)
add_para('在一个 Agent 系统中，Runtime 是 LLM 和工具之间的"调度器"。')
add_para('用户浏览器（Web UI）→ Flask Server（server.py）→ Runtime.run(session, message) → \n  ├── 调用 LLM（llm.py）\n  ├── 执行工具（tools/registry.py）\n  └── 管理上下文（_maybe_compress）\n  → AgentResponse → Server → Web UI')
add_para('LLM 只输出 token，不执行任何代码。Runtime 是替 LLM"干活"的那只手。整个调度循环完全由 Runtime 维护。')

doc.add_heading('1.2 数据结构的设计意图', level=2)
add_para('Runtime 通过三个数据类定义与外部世界的合约：', bold=True)
add_para('ToolTrace：记录单次工具调用的完整信息（名称、参数、结果、耗时、是否异步），服务于前端展示和开发者调试。')
add_para('AgentResponse：Runtime 处理完一轮的完整结果（final_text、tool_traces、turns_used、context_tokens）。server.py 只依赖这个结构。')
add_para('RuntimeConfig：可调参数集合（max_turns、max_context_tokens、recent_full_rounds、system_prompt），通过环境变量覆盖默认值。')

doc.add_heading('1.3 核心循环 run() 方法逐段解读', level=2)

add_para('准备阶段', bold=True)
add_para('用户消息追加到 session.messages（持久化），然后构建临时 messages 列表，以 system_prompt 开头 + 全部历史。关键设计：messages（本轮使用，含 system prompt）和 session.messages（持久化，不含 system prompt）是两个独立列表，避免恢复时 system prompt 重复。')

add_para('循环体：Agent Loop 的本质', bold=True)
add_para('核心逻辑三步：调 LLM → 看返回值（纯文本就结束，有 tool_calls 就执行）→ 工具结果回填后继续。每次 LLM 调用前做 context 压缩检查。max_turns 是安全阀。')

add_para('工具执行：Runtime 存在的理由', bold=True)
add_para('LLM 输出的 tool_calls 只是 JSON 数组。Runtime 接到后找到 registry 中对应的 Python 函数，await 执行，把结果包装成 OpenAI 兼容的 tool result 消息塞回 messages。tool_call_id 必须严格对应。')

add_para('兜底逻辑：强制终止', bold=True)
add_para('达到 max_turns 时注入系统消息"请基于已获取信息给出最终结论"，然后调 LLM 但不带 tools 参数——防止 LLM 又想调工具导致死循环。')

doc.add_heading('1.4 Context 压缩策略', level=2)
add_para('策略核心：截短旧数据，而非删除。直接删除可能切断对话上下文。recent_full_rounds=3 确保最近 3 轮完整保留。更旧的 tool_result 截短到 300 字符。更完善的方案可用 LLM 对旧轮次做摘要生成。')

doc.add_heading('1.5 异常处理机制', level=2)
add_para('三层异常处理：', bold=True)
add_bullet('LLM 调用层：_call_llm_with_retry 自动重试 2 次，递增等待（2s/4s）')
add_bullet('工具执行层：_execute_tool_safely 拦截三类异常——未知工具名（LLM 幻觉）返回可用工具列表、参数错误返回提示让 LLM 自修正、工具内部异常返回错误详情')
add_bullet('重复调用检测：同一工具+同一参数连续出现时强制终止，防止 LLM 在 check_task 等轮询场景中死循环')
add_para('最外层还有 try/except 兜底，确保任何未预期异常都返回友好提示而非崩溃。')

doc.add_heading('1.6 Token 估算的取舍', level=2)
add_para('用 len(v)//2 估算而非 tiktoken。原因：DeepSeek 无公开 tokenizer；判断"是否快爆了"不需要精确到个位，误差 20% 内足够。')

doc.add_heading('1.7 Runtime 完成度对照', level=2)
add_table(
    ['要求', '状态', '实现方式'],
    [
        ['Agent Loop', '已完成', 'while turns < max_turns + 文本/工具分支'],
        ['工具调度', '已完成', 'ToolRegistry.execute 统一入口'],
        ['Session 隔离', '已完成', 'Session.messages 独立 + SessionStore'],
        ['Context 压缩', '已完成', '_maybe_compress 截短旧 tool_result'],
        ['最大轮次', '已完成', 'max_turns + 强制总结 + 不带 tools'],
        ['异步工具', '已完成', 'LLM 调 check_task + asyncio 后台执行'],
        ['异常处理', '已完成', 'LLM 重试 + 幻觉拦截 + 重复检测'],
        ['Trace 日志', '已完成', 'ToolTrace 记录 + logging 输出'],
    ]
)
doc.add_page_break()

# ═══ CHAPTER 2 ═══
doc.add_heading('第二章：面试官视角——从零构建 Agent 框架核心提问', level=1)

questions = [
    ("2.1 设计一个 Agent Loop，核心循环怎么写？",
     "考察候选人是否真正理解 Agent 工作机制。区分"理解原理"和"只会用框架"。",
     "核心是 while 循环：调 LLM → 解析 → 有 tool_calls 就执行工具 → 结果回填 → 继续 / 纯文本就返回用户。每次循环完成一次 think-act-observe。tool_call_id 必须与 tool result 中的 id 对应。max_turns 是安全阀。"),

    ("2.2 同步工具和异步工具的区别？Runtime 如何处理？",
     "考察对真实世界约束的理解。数据分析中 SQL 可能跑几分钟，不能同步等。",
     "同步工具调用即得结果；异步工具返回 task_id，后台执行。Runtime 收到 pending 后把 task_id 告诉 LLM，让 LLM 自主决定轮询时机。更优方案：Runtime 维护 pending_tasks，后台完成时主动通知 LLM。"),

    ("2.3 多 Session 如何隔离？并发会互相影响吗？",
     "考察对状态管理和并发的理解。Agent 不能是单机玩具。",
     "每个 Session 独立持有 messages + metadata。SessionStore 用 dict[session_id] 管理，通过 session_id 路由。同 session 不并发调用，不同 session 完全并行。async/await 在 IO 期间自然让出控制权。需要锁的场景：同一 session 允许并发修改时用 asyncio.Lock。"),

    ("2.4 Context 太长怎么办？",
     "这是架构设计题模块一的直接映射。考察多层次压缩策略。",
     "四层方案：① 数据裁剪——大结果只保留前 N 行+摘要 ② LLM 摘要——旧轮次用 LLM 生成压缩摘要 ③ 滑动窗口——保留最近 N 轮完整+早期摘要 ④ 结构化记忆——关键事实抽取到 memory store。压缩时机应在每轮前检查，防止单轮爆掉。"),

    ("2.5 LLM 调了不存在的工具（幻觉）怎么办？",
     "考察容错设计。LLM 是不可靠组件，Runtime 要防错而非信任。",
     'Registry 查不到时返回结构化错误：{error: "工具不存在，可用: ..."}，回填给 LLM 让其自修正。同幻觉连续 3 次后强制终止。参数格式错误同理：返回错误消息让 LLM 修正。可维护错误计数器，达阈值后降级为不带 tools 直接回答。'),

    ("2.6 LLM 死循环怎么办？",
     "考察故障模式理解。Agent 不是每次都完美工作。",
     "多层兜底：max_turns 基础限制、同工具同参数连续检测（3次即终止）、无进展检测（tool_result 一直 error/pending）、token 消耗兜底、超时总限。达到兜底后不带 tools 调 LLM 做最佳回复。"),

    ("2.7 Claude Code 工具输出 vs OpenAI function calling？",
     "架构设计题模块五。考察对不同 Agent 范式的独立分析能力。",
     "OpenAI：工具定义在 tools 参数，LLM 返回结构化 tool_calls JSON，结果通过 role=tool 回填。优点是结构清晰、可验证、适合生产。缺点是格式僵化。Claude Code：工具结果以文本块嵌入对话流，思考与工具调用交错。优点是灵活自然，缺点是解析不稳定。前者适合企业场景，后者适合探索性交互。"),

    ("2.8 让 Agent 每天早上 9 点自动跑任务？",
     "架构设计题模块三。考察从同步请求-响应到异步调度的思维转变。",
     "需要 Task Scheduler 模块（独立进程）。Cron 定义触发时间，到时间创建系统 Session 调 Runtime.run()。结果需要 Notification 通道（消息列表/日报文件/通知）。需失败重试+日志。架构变化：单进程 → 多进程（Server+Scheduler+Worker），需共享存储（Redis/PostgreSQL）。"),

    ("2.9 200 轮后用户问以前问过的问题，怎么做 Memory 召回？",
     "架构设计题模块二。长对话历史已被压缩或丢弃，如何在压缩信息中找回需要的内容。",
     "Memory 分层：短期（最近 N 轮完整）、中期（压缩摘要）、长期（结构化事实抽取）。召回策略：向量检索+事实提取，每轮结束后异步抽取关键事实以向量存入 memory store，提问时语义相似度检索。时间衰减权重。经典框架参考：MemGPT 的虚拟上下文管理。趋势：无结构全历史 → 结构化事实图谱+摘要。"),

    ("2.10 从零写 vs 用 LangChain？",
     "开放题，考察反思能力和学习深度。需要说清框架隐藏了什么以及理解那些隐藏物的价值。",
     "LangChain 替你做了 AgentExecutor（Loop）、BaseTool（工具抽象）、Memory 系统、Callback 系统。从零写让你理解：每条消息怎么拼、tool_call_id 为什么要对上、异步工具的二段式交互、context 压缩的时机和粒度。最大收获是"去掉魔法"——理解了每个消息块的流向。200 行自研代码 vs 5000 行依赖链。最佳实践：LangChain 做原型 → 自研替换关键路径。"),
]

for q_title, intent, answer in questions:
    doc.add_heading(q_title, level=2)
    add_para('考官意图', bold=True)
    add_para(intent)
    add_para('参考答案要点', bold=True)
    add_para(answer)

doc.add_page_break()
doc.add_heading('附录：项目文件索引', level=1)
add_table(
    ['文件', '作用'],
    [
        ['src/runtime.py', '核心调度引擎：Loop、工具调度、异常处理、Context 压缩'],
        ['src/llm.py', 'AsyncOpenAI 封装、System Prompt'],
        ['src/tools/registry.py', 'ToolRegistry 工具注册与执行'],
        ['src/tools/run_sql.py', '异步 PostgreSQL 查询 + check_task'],
        ['src/tools/chart.py', 'matplotlib 图表生成'],
        ['src/tools/report.py', 'Markdown 报告导出'],
        ['src/session.py', 'Session 数据类 + SessionStore'],
        ['src/server.py', 'Flask Web 服务 + REST API'],
        ['src/config.py', '环境变量配置'],
        ['static/index.html', 'Web UI（多会话/追踪面板）'],
        ['data/setup.py', 'PostgreSQL 建表+数据'],
    ]
)

output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Agent-Runtime学习笔记.docx')
doc.save(output_path)
print(f'OK: {output_path}')
