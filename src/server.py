"""Flask web server — REST API + static frontend."""

import uuid
import json
import time
import asyncio
import logging
from flask import Flask, request, jsonify, send_from_directory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

from src.llm import LLMClient
from src.session import SessionStore
from src.tools.registry import ToolRegistry, ToolDef
from src.tools.run_sql import run_sql, check_task, TOOL_DEF as SQL_TOOL_DEF, CHECK_TASK_DEF
import src.tools.run_sql as sql_mod
from src.tools.chart import generate_chart, TOOL_DEF as CHART_TOOL_DEF
from src.tools.report import export_report, TOOL_DEF as REPORT_TOOL_DEF

# 尝试导入 Runtime（如果你还没实现，就用占位模式）
RUNTIME_READY = False
try:
    from src.runtime import Runtime, RuntimeConfig
    RUNTIME_READY = True
except (ImportError, NotImplementedError):
    pass

app = Flask(__name__, static_folder="../static", static_url_path="")

# ── 初始化依赖 ──
session_store = SessionStore(persist_dir="sessions")
llm_client = LLMClient()
tool_registry = ToolRegistry()
tool_registry.register(ToolDef(**SQL_TOOL_DEF, execute=run_sql, is_async=True))
tool_registry.register(ToolDef(**CHECK_TASK_DEF, execute=check_task))
tool_registry.register(ToolDef(**CHART_TOOL_DEF, execute=generate_chart))
tool_registry.register(ToolDef(**REPORT_TOOL_DEF, execute=export_report))

runtime = Runtime(llm_client, tool_registry) if RUNTIME_READY else None


# ── 辅助函数 ──
def _generate_id():
    return uuid.uuid4().hex[:8]


def _to_chat_message(msg: dict) -> dict:
    """Convert internal message dict to frontend-friendly format."""
    msg_type = msg.get("role", "unknown")
    if msg_type == "tool":
        return {
            "role": "tool",
            "content": f"[工具结果]\n{msg.get('content', '')[:500]}",
        }
    if msg_type == "assistant" and msg.get("tool_calls"):
        tools = [tc["function"]["name"] for tc in msg["tool_calls"]]
        return {
            "role": "assistant",
            "content": msg.get("content") or f"🔧 调用工具: {', '.join(tools)}",
            "tool_calls": msg["tool_calls"],
        }
    return {"role": msg_type, "content": msg.get("content", "")}


# ── API 路由 ──

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "runtime_ready": RUNTIME_READY})


@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    sessions = session_store.list_sessions()
    return jsonify([
        {
            "session_id": s.session_id,
            "name": s.name,
            "message_count": len(s.messages),
            "created_at": s.created_at,
            "last_active_at": s.last_active_at,
        }
        for s in sessions
    ])


@app.route("/api/sessions", methods=["POST"])
def create_session():
    data = request.get_json() or {}
    sid = _generate_id()
    name = data.get("name", f"会话 {sid}")
    session = session_store.create(sid, name)
    session_store.save(session)
    return jsonify({"session_id": sid, "name": name})


@app.route("/api/sessions/<sid>", methods=["DELETE"])
def delete_session(sid):
    s = session_store.get(sid)
    if s:
        import os
        path = os.path.join("sessions", f"{sid}.json")
        if os.path.exists(path):
            os.remove(path)
        session_store._sessions.pop(sid, None)
        return jsonify({"status": "deleted"})
    return jsonify({"error": "Session not found"}), 404


@app.route("/api/sessions/<sid>/history")
def get_history(sid):
    s = session_store.get(sid)
    if not s:
        return jsonify({"error": "Session not found"}), 404
    return jsonify([_to_chat_message(m) for m in s.messages])


@app.route("/api/sessions/<sid>/chat", methods=["POST"])
def chat(sid):
    if not RUNTIME_READY:
        return jsonify({
            "error": "Runtime 尚未实现！请先完成 src/runtime.py 中的 Runtime.run() 方法。",
            "reply": "Runtime 未就绪。",
        }), 503

    s = session_store.get(sid)
    if not s:
        return jsonify({"error": "Session not found"}), 404

    data = request.get_json() or {}
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    loop = None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        response = loop.run_until_complete(runtime.run(s, user_message))
    except NotImplementedError:
        return jsonify({
            "error": "Runtime.run() 尚未实现！",
            "reply": "Runtime 未就绪。",
        }), 503
    except Exception as e:
        return jsonify({"error": str(e), "reply": f"出错了: {str(e)}"}), 500
    finally:
        if loop is not None:
            # 清理 asyncpg pool（绑定到当前事件循环，loop 关闭后连接失效）
            if sql_mod._pool is not None:
                try:
                    loop.run_until_complete(sql_mod._pool.close())
                except Exception:
                    pass
            sql_mod._pool = None
            loop.close()

    session_store.save(s)

    return jsonify({
        "reply": response.final_text,
        "tool_traces": [
            {
                "tool_name": t.tool_name,
                "arguments": t.arguments,
                "result_summary": t.result_summary,
                "duration_ms": t.duration_ms,
                "is_async": t.is_async,
                "task_id": t.task_id,
            }
            for t in response.tool_traces
        ],
        "turns_used": response.turns_used,
        "context_tokens": response.context_tokens,
    })


# ── 静态文件 ──

@app.route("/")
def index():
    return send_from_directory("../static", "index.html")


@app.route("/reports/<path:fname>")
def serve_report(fname):
    import os
    return send_from_directory(os.path.abspath("../reports"), fname)


if __name__ == "__main__":
    print(f" Runtime 状态: {'已就绪' if RUNTIME_READY else '待实现 — src/runtime.py'}")
    print(f" 工具已注册: {[t.name for t in tool_registry._tools.values()]}")
    print(" 启动: http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
