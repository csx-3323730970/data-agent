"""Tool Registry — register, describe, and execute tools."""

import json
from dataclasses import dataclass, field
from collections.abc import Callable, Awaitable


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict  # JSON Schema for the tool's parameters
    execute: Callable[..., Awaitable[str]]
    is_async: bool = False

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef):
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def get_schemas(self) -> list[dict]:
        return [t.to_openai_schema() for t in self._tools.values()]

    async def execute(self, name: str, arguments: str) -> str:
        """Execute a tool by name. Returns the result string or error message."""
        tool = self._tools.get(name)
        if not tool:
            return json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
        except json.JSONDecodeError:
            return json.dumps({"error": f"Invalid JSON arguments: {arguments}"}, ensure_ascii=False)
        try:
            result = await tool.execute(**args)
            return result
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
