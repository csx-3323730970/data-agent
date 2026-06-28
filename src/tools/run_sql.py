"""run_sql tool — async PostgreSQL query (simulates long queries with delay)."""

import json
import time
import asyncio
import uuid
import asyncpg
from src.config import PG_DSN, SQL_TIMEOUT_SECONDS, ASYNC_DELAY_SECONDS

_pool: asyncpg.Pool | None = None
_task_store: dict[str, dict] = {}


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(PG_DSN, min_size=2, max_size=10)
    return _pool


async def _build_tables_summary() -> str:
    """Return a summary of all tables and their schemas."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)

        lines = ["## 数据库表概览\n"]
        for t in tables:
            tname = t["table_name"]
            count = await conn.fetchval(f'SELECT COUNT(*) FROM "{tname}"')
            cols = await conn.fetch("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = $1
                ORDER BY ordinal_position
            """, tname)
            lines.append(f"### {tname}（{count} 行）")
            for c in cols:
                lines.append(f"  {c['column_name']} ({c['data_type']})")
            lines.append("")
    return "\n".join(lines)


async def run_sql(query: str, explain: str = "") -> str:
    """Execute a SQL query. Async — returns task_id immediately, use check_task to poll results.

    Args:
        query: SQL query to execute (read-only SELECT)
        explain: Short description for logging
    """
    task_id = f"sql-{uuid.uuid4().hex[:8]}"
    _task_store[task_id] = {"status": "pending", "query": query, "explain": explain}

    _ = asyncio.create_task(_run_sql_async(task_id, query))
    return json.dumps({
        "task_id": task_id,
        "status": "pending",
        "message": f"查询已提交，预计 {ASYNC_DELAY_SECONDS} 秒后完成。请用 check_task 轮询结果。",
    }, ensure_ascii=False)


async def _run_sql_async(task_id: str, query: str):
    """Background task: execute SQL after artificial delay."""
    try:
        await asyncio.sleep(ASYNC_DELAY_SECONDS)
        pool = await _get_pool()
        async with pool.acquire() as conn:
            start = time.time()

            just_table_info = query.strip().lower() == "__tables__"
            if just_table_info:
                result = await _build_tables_summary()
                columns = []
                rows = []
                row_count = 0
            else:
                rows = await conn.fetch(query, timeout=SQL_TIMEOUT_SECONDS)
                columns = list(rows[0].keys()) if rows else []
                rows = [list(r.values()) for r in rows]
                row_count = len(rows)
                result = _format_result(columns, rows)

            elapsed = time.time() - start
            _task_store[task_id] = {
                "status": "done",
                "query": query,
                "columns": columns,
                "row_count": row_count,
                "result": result,
                "elapsed_seconds": round(elapsed, 3),
            }
    except Exception as e:
        _task_store[task_id] = {"status": "error", "query": query, "error": str(e)}


def _format_result(columns: list[str], rows: list[list], max_rows: int = 50) -> str:
    if not rows:
        return "查询结果为空。"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body_rows = rows[:max_rows]
    body = "\n".join(
        "| " + " | ".join(str(v) if v is not None else "NULL" for v in row) + " |"
        for row in body_rows
    )
    result = f"{header}\n{sep}\n{body}"
    if len(rows) > max_rows:
        result += f"\n\n*（仅展示前 {max_rows} 行，共 {len(rows)} 行）*"
    return result


async def check_task(task_id: str) -> str:
    """Poll the status of an async SQL task."""
    task = _task_store.get(task_id)
    if not task:
        return json.dumps({"error": f"未知的 task_id: {task_id}"}, ensure_ascii=False)

    if task["status"] == "pending":
        return json.dumps({
            "task_id": task_id,
            "status": "pending",
            "message": "查询仍在执行中...",
        }, ensure_ascii=False)

    if task["status"] == "error":
        return json.dumps({
            "task_id": task_id,
            "status": "error",
            "error": task["error"],
        }, ensure_ascii=False)

    return json.dumps({
        "task_id": task_id,
        "status": "done",
        "columns": task["columns"],
        "row_count": task["row_count"],
        "result": task["result"],
        "elapsed_seconds": task["elapsed_seconds"],
    }, ensure_ascii=False)


TOOL_DEF = {
    "name": "run_sql",
    "description": "执行 SQL 查询（PostgreSQL）。异步工具：调用后返回 task_id，用 check_task 轮询获取结果。传 query='__tables__' 可查看所有表结构。",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "SQL 查询语句（只读 SELECT）。或传 '__tables__' 查看数据库表结构。",
            },
            "explain": {
                "type": "string",
                "description": "简短描述这个查询的目的，用于日志追踪",
            },
        },
        "required": ["query"],
    },
}

CHECK_TASK_DEF = {
    "name": "check_task",
    "description": "轮询异步任务的结果。当 run_sql 返回 pending 状态时，用此工具获取最终结果。",
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "run_sql 返回的 task_id",
            },
        },
        "required": ["task_id"],
    },
}
