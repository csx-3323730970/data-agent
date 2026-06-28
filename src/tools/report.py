"""export_report tool — export analysis as Markdown report."""

import json
import os
import time

REPORT_DIR = "reports"
os.makedirs(REPORT_DIR, exist_ok=True)


async def export_report(title: str, content: str) -> str:
    """Export analysis results as a Markdown report. Synchronous.

    Args:
        title: Report title
        content: Markdown content of the report
    """
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    fname = f"report_{int(time.time())}.md"
    fpath = os.path.join(REPORT_DIR, fname)

    full_content = f"""# {title}

> 生成时间：{timestamp}

{content}
"""
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(full_content)

    return json.dumps({
        "status": "done",
        "file": fpath,
        "title": title,
    }, ensure_ascii=False)


TOOL_DEF = {
    "name": "export_report",
    "description": "将分析过程和结论导出为 Markdown 报告文件。",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "报告标题",
            },
            "content": {
                "type": "string",
                "description": "报告的 Markdown 内容，包含分析过程、图表引用和结论",
            },
        },
        "required": ["title", "content"],
    },
}
