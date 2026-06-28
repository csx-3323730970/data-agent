"""Core Agent Runtime。

Runtime 的角色：LLM 和工具之间的"调度器"。

用户说一句话 → Runtime 把它交给 LLM →
  LLM 说"我需要调 run_sql" → Runtime 去执行 run_sql →
  Runtime 把结果交还给 LLM → LLM 说"数据查到了，回复是..." →
  Runtime 把最终回复返回给用户

LLM 只输出 token，不执行任何代码。Runtime 是替 LLM"干活"的那只手。
"""

import json
import time
import asyncio
import logging
from dataclasses import dataclass, field
from src.llm import LLMClient, SYSTEM_PROMPT
from src.tools.registry import ToolRegistry
from src.config import MAX_TURNS, CONTEXT_MAX_TOKENS, RECENT_FULL_ROUNDS

logger = logging.getLogger("runtime")
LLM_MAX_RETRIES = 2
SAME_TOOL_REPEAT_LIMIT = 3

# ═══════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════

@dataclass
class ToolTrace:
    tool_name: str
    arguments: str
    result_summary: str
    duration_ms: float
    is_async: bool = False
    task_id: str = ""


@dataclass
class AgentResponse:
    final_text: str
    tool_traces: list[ToolTrace] = field(default_factory=list)
    turns_used: int = 0
    context_tokens: int = 0


@dataclass
class RuntimeConfig:
    max_turns: int = MAX_TURNS
    max_context_tokens: int = CONTEXT_MAX_TOKENS
    recent_full_rounds: int = RECENT_FULL_ROUNDS
    system_prompt: str = SYSTEM_PROMPT


# ═══════════════════════════════════════════
# Runtime
# ═══════════════════════════════════════════

class Runtime:

    def __init__(self, llm_client: LLMClient, tool_registry: ToolRegistry,
                 config: RuntimeConfig | None = None):
        self.llm = llm_client
        self.registry = tool_registry
        self.config = config or RuntimeConfig()
        self.tools_schema = tool_registry.get_schemas()

    # ── LLM 调用（带重试）──────────────────────────

    async def _call_llm_with_retry(self, messages: list[dict],
                                   tools: list[dict] | None = None,
                                   max_retries: int = LLM_MAX_RETRIES) -> dict:
        """调 LLM，失败时自动重试。

        - 网络错误/超时 → 等一会重试，最多 max_retries 次
        - 重试期间 LLM 看不到错误信息（避免干扰推理）
        """
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return await self.llm.chat(messages, tools=tools)
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    wait = (attempt + 1) * 2  # 2s, 4s 递增等待
                    logger.warning(
                        "LLM 调用失败 (attempt %s/%s): %s，%ss 后重试",
                        attempt + 1, max_retries + 1, e, wait
                    )
                    await asyncio.sleep(wait)
        # 所有重试都失败了
        raise RuntimeError(f"LLM 调用失败，已重试 {max_retries} 次: {last_error}")

    # ── 主入口 ──────────────────────────────────────

    async def run(self, session, user_message: str) -> AgentResponse:
        """处理一条用户消息，跑完整个 Agent Loop 后返回最终回复。"""
        traces: list[ToolTrace] = []
        turns = 0
        last_tool_fingerprint = ("", "")   # (tool_name, tool_args) 用于检测重复调用

        # 1. 用户消息写入历史
        session.messages.append({"role": "user", "content": user_message})

        # 2. 构建完整的 messages 列表发给 LLM
        messages = [{"role": "system", "content": self.config.system_prompt}]
        messages.extend(session.messages)

        # 3. Agent Loop
        try:
            while turns < self.config.max_turns:
                turns += 1
                messages = self._maybe_compress(messages)

                # ── 调 LLM（带重试）──
                try:
                    response = await self._call_llm_with_retry(
                        messages, tools=self.tools_schema
                    )
                except RuntimeError as e:
                    logger.error("LLM 不可用，终止循环: %s", e)
                    return AgentResponse(
                        final_text=f"抱歉，AI 服务暂时不可用，请稍后重试。",
                        tool_traces=traces,
                        turns_used=turns,
                    )

                messages.append(response)
                session.messages.append(response)

                tool_calls = response.get("tool_calls", [])

                # 情况 A：纯文本回复 —— 任务完成
                if not tool_calls:
                    return AgentResponse(
                        final_text=response.get("content") or "",
                        tool_traces=traces,
                        turns_used=turns,
                        context_tokens=self._estimate_tokens(messages),
                    )

                # 情况 B：LLM 要调工具
                for tc in tool_calls:
                    fn = tc["function"]
                    tool_name = fn["name"]
                    tool_args = fn["arguments"]

                    # ── 重复调用检测 ──
                    fingerprint = (tool_name, tool_args)
                    if fingerprint == last_tool_fingerprint:
                        logger.warning(
                            "检测到连续重复调用: %s(%s)，强制终止并让 LLM 总结",
                            tool_name, tool_args[:100]
                        )
                        messages.append({
                            "role": "user",
                            "content": (
                                f"你已经连续多次调用 {tool_name} 且参数不变。"
                                "请基于已获取的信息直接回答用户。"
                            )
                        })
                        final = await self._call_llm_with_retry(messages)
                        session.messages.append(messages[-1])
                        session.messages.append(final)
                        return AgentResponse(
                            final_text=final.get("content") or "",
                            tool_traces=traces,
                            turns_used=turns,
                            context_tokens=self._estimate_tokens(messages),
                        )
                    last_tool_fingerprint = fingerprint

                    # ── 执行工具（带错处理）──
                    t0 = time.perf_counter()
                    result_str = await self._execute_tool_safely(
                        tc["id"], tool_name, tool_args
                    )
                    elapsed_ms = (time.perf_counter() - t0) * 1000

                    result_msg = {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result_str,
                    }
                    messages.append(result_msg)
                    session.messages.append(result_msg)

                    traces.append(ToolTrace(
                        tool_name=tool_name,
                        arguments=tool_args,
                        result_summary=self._summarize_result(result_str),
                        duration_ms=round(elapsed_ms, 1),
                    ))

            # 4. 达到最大轮次，强制总结
            messages.append({
                "role": "user",
                "content": "已达到最大轮次限制，请基于已获取的信息给出最终结论。"
            })
            try:
                final = await self._call_llm_with_retry(messages)
            except RuntimeError:
                final = {
                    "role": "assistant",
                    "content": "抱歉，分析超时。请尝试简化问题后重新提问。"
                }
            session.messages.append(final)

            return AgentResponse(
                final_text=final.get("content") or "抱歉，未能完成分析。",
                tool_traces=traces,
                turns_used=turns,
                context_tokens=self._estimate_tokens(messages),
            )

        except Exception as e:
            logger.error("Runtime 未预期异常: %s", e, exc_info=True)
            return AgentResponse(
                final_text=f"抱歉，系统出现异常，请稍后重试。",
                tool_traces=traces,
                turns_used=turns,
            )

    # ── 工具执行（安全包装）──────────────────────

    async def _execute_tool_safely(self, call_id: str, tool_name: str,
                                   tool_args: str) -> str:
        """执行工具，三类异常都转为 LLM 能理解的错误消息。

        1. 工具不存在（LLM 幻觉）→ 返回可用工具列表
        2. 参数 JSON 格式错误 → 返回原始参数 + 错误提示
        3. 工具内部执行异常 → 返回错误信息让 LLM 自修正
        """
        # 检测未知工具：registry 里没有就是幻觉
        if self.registry.get(tool_name) is None:
            available = ", ".join(
                t.name for t in self.registry._tools.values()
            )
            return json.dumps({
                "error": f"工具 '{tool_name}' 不存在。可用工具: {available}",
                "tool_call_id": call_id,
            }, ensure_ascii=False)

        try:
            return await self.registry.execute(tool_name, tool_args)
        except Exception as e:
            logger.warning("工具 %s 执行异常: %s", tool_name, e)
            return json.dumps({
                "error": f"工具 '{tool_name}' 执行失败: {str(e)}",
                "tool_call_id": call_id,
                "hint": "请检查参数是否正确，或尝试其他方式完成用户需求。",
            }, ensure_ascii=False)

    # ── 辅助方法 ────────────────────────────────────

    def _maybe_compress(self, messages: list[dict]) -> list[dict]:
        """如果 messages 估算 token 超过阈值，做基础裁剪。"""
        if self._estimate_tokens(messages) < self.config.max_context_tokens:
            return messages

        keep_from = len(messages)
        found = 0
        for i in range(len(messages) - 1, -1, -1):
            m = messages[i]
            if m["role"] in ("user", "assistant") and m.get("content"):
                found += 1
            if found >= self.config.recent_full_rounds * 2:
                keep_from = i + 1
                break

        for i in range(keep_from):
            if messages[i]["role"] == "tool" and i > 0:
                content = messages[i].get("content", "")
                if len(content) > 300:
                    messages[i]["content"] = content[:300] + "...（已截断）"

        return messages

    def _estimate_tokens(self, messages: list[dict]) -> int:
        total = 0
        for m in messages:
            for v in m.values():
                if isinstance(v, str):
                    total += len(v) // 2 + 1
        return total

    def _summarize_result(self, result_str: str) -> str:
        try:
            data = json.loads(result_str)
        except json.JSONDecodeError:
            return result_str[:100]
        if "error" in data:
            return f"失败: {data['error'][:80]}"
        if data.get("status") == "pending":
            return f"已提交，task_id={data.get('task_id', '?')}"
        if data.get("status") == "done":
            rows = data.get("row_count", "?")
            return f"完成，返回 {rows} 行"
        if "file" in data:
            return f"文件已生成: {data['file']}"
        return "完成"
