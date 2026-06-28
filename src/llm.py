"""DeepSeek LLM client wrapper — OpenAI-compatible async interface."""

from openai import AsyncOpenAI
from src.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

SYSTEM_PROMPT = """你是一个数据分析助手 Agent。使用工具帮用户完成数据分析任务。

规则：
1. 数据分析时，先用 run_sql 查数据，再用 generate_chart 画图，最后用 export_report 导出报告
2. run_sql 是异步工具，返回 task_id 后用 check_task 轮询结果
3. 工具返回的数据可能很大，做归纳总结，不要直接复制原始数据
4. 追问时基于前文结果继续分析，不重复查询
5. 全程用中文

回复格式要求：
- 禁止使用 markdown 语法：不要用 ** 加粗、不要用 | 画表格、不要用 ## 标题、不要用 ``` 代码块
- 禁止使用 emoji（如 👋📊🧠😊✅）
- 使用自然段落和平实的文字描述。列举时用换行加短横线即可
- 语气简洁、专业，像一位数据分析师在汇报"""



class LLMClient:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
        self.model = LLM_MODEL

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """Send messages to LLM, return the response message dict.

        Returns a message dict with either 'content' (text reply) or
        'tool_calls' (tool calls requested).
        """
        kwargs = dict(
            model=self.model,
            messages=messages,
            temperature=0.1,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self.client.chat.completions.create(**kwargs)
        choice = response.choices[0].message

        if choice.tool_calls:
            return {
                "role": "assistant",
                "content": choice.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in choice.tool_calls
                ],
            }
        else:
            return {"role": "assistant", "content": choice.content}
