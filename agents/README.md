# Agent interfaces

Generated from the Pydantic models in `tkcore/agent_tools.py` by `python -m tkcore.agent_tools emit`. CI fails if these files go stale (`python -m tkcore.agent_tools --check`).

| file | for |
|---|---|
| `tools.json` | tool definitions with `input_schema`, for APIs that take that shape |
| `tools.openai.json` | OpenAI function tools, strict mode |
| `openapi.json` | `python -m tkcore.agent_tools serve` (HTTP, OpenAPI 3.1) |
| `schemas/<tool>.input.json`, `schemas/<tool>.output.json` | JSON Schema 2020-12 for every tool's arguments and result |
| `skills/thirukkural/` | an Agent Skill (`SKILL.md` and its script); written by hand |

The MCP server is `python -m tkcore.mcp_server`. Whichever interface you use, run the tool calls on your side with `tkcore.agent_tools.call(name, arguments)`.
