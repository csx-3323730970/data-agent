"""generate_chart tool — synchronous chart generation with matplotlib."""

import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

CHART_DIR = "reports"

# 中文字体回退
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

os.makedirs(CHART_DIR, exist_ok=True)


async def generate_chart(data_json: str, chart_type: str, title: str = "",
                         x_label: str = "", y_label: str = "") -> str:
    """Generate a chart from JSON data. Synchronous.

    Args:
        data_json: JSON string of {labels: [...], values: [...], series: [...]}
        chart_type: One of bar, line, pie
        title: Chart title
        x_label: X-axis label
        y_label: Y-axis label
    """
    try:
        data = json.loads(data_json) if isinstance(data_json, str) else data_json
    except json.JSONDecodeError:
        return json.dumps({"error": "data_json 格式不正确，需要合法的 JSON"}, ensure_ascii=False)

    labels = data.get("labels", [])
    values = data.get("values", [])
    series = data.get("series", None)  # Optional: [{name, values}]

    if not labels or not values:
        return json.dumps({"error": "data_json 必须包含 labels 和 values"}, ensure_ascii=False)

    fig, ax = plt.subplots(figsize=(10, 5))

    if series:
        bar_width = 0.8 / len(series)
        x = range(len(labels))
        for i, s in enumerate(series):
            offset = [pos + i * bar_width for pos in x]
            ax.bar(offset, s["values"], bar_width, label=s["name"])
        ax.set_xticks([pos + bar_width * (len(series) - 1) / 2 for pos in x])
        ax.set_xticklabels(labels, rotation=30, ha="right")
        ax.legend()
    elif chart_type == "bar":
        ax.bar(labels, values)
    elif chart_type == "line":
        ax.plot(labels, values, marker="o")
    elif chart_type == "pie":
        ax.pie(values, labels=labels, autopct="%1.1f%%")
    else:
        ax.bar(labels, values)

    ax.set_title(title)
    if x_label and chart_type != "pie":
        ax.set_xlabel(x_label)
    if y_label and chart_type != "pie":
        ax.set_ylabel(y_label)

    fig.tight_layout()

    import time
    fname = f"chart_{int(time.time() * 1000)}.png"
    fpath = os.path.join(CHART_DIR, fname)
    fig.savefig(fpath, dpi=120)
    plt.close(fig)

    return json.dumps({
        "status": "done",
        "file": fpath,
        "chart_type": chart_type,
        "title": title,
    }, ensure_ascii=False)


TOOL_DEF = {
    "name": "generate_chart",
    "description": "根据数据生成图表（柱状图/折线图/饼图），返回图片文件路径。data_json 格式：{\"labels\": [...], \"values\": [...], \"series\": [{\"name\": \"...\", \"values\": [...]}]}（series 可选）",
    "parameters": {
        "type": "object",
        "properties": {
            "data_json": {
                "type": "string",
                "description": "JSON 字符串，包含 labels（标签列表）和 values（数值列表），可选 series（多系列数据）",
            },
            "chart_type": {
                "type": "string",
                "enum": ["bar", "line", "pie"],
                "description": "图表类型",
            },
            "title": {
                "type": "string",
                "description": "图表标题",
            },
            "x_label": {
                "type": "string",
                "description": "X 轴标签",
            },
            "y_label": {
                "type": "string",
                "description": "Y 轴标签",
            },
        },
        "required": ["data_json", "chart_type"],
    },
}
