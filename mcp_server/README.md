# JK Assistance MCP server

Exposes JK Assistance's knowledge base and rule engines as MCP tools, so Claude Desktop, Claude Code or any MCP client can answer AJK admission, document, fee, deadline and semester-promotion questions, grounded in official sources.

## Run

```bash
python mcp_server/server.py
```

That runs over stdio (what Claude Desktop / Claude Code launch). For remote clients or the MCP Inspector, use Streamable HTTP on `http://localhost:8765/mcp`:

```bash
python mcp_server/server.py --http
```

## Configure a client

Claude Code (`.mcp.json` in your project) or Claude Desktop (`%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "jk-assistance": {
      "command": "python",
      "args": ["C:\\Users\\Faisal Ramzan\\Desktop\\AJK university VA\\mcp_server\\server.py"],
      "env": {"JK_DISABLE_LLM": "1"}
    }
  }
}
```

Use the full path to the Python interpreter that has `requirements.txt` installed if `python` is not on PATH.

## Tools

| Tool | Purpose |
|---|---|
| `advise_admission` | Programs a 12th-grade student can apply for, with chance (heuristic), tests, fees, documents, how to apply and deadlines |
| `list_services` / `get_service` | Degree, transcript, verification, migration, clearance, bonafide... checklists with the fee in force today |
| `get_deadlines` | Admission and merit-list dates, fee fine windows, re-checking and registration rules |
| `evaluate_progression` | MUST promotion/probation/relegation and GPA/CGPA from a transcript |
| `student_dashboard` | Proactive findings for a stored student (GUIDE / ASK_INFO / ALERT / ESCALATE) |
| `start_application` | Open a tracked application case |
| `search_knowledge` | Evidence search over all fetched official pages and documents |
| `ask_jk_assistance` | The complete assistant pipeline for a free-text question |

## Smoke test

```bash
python scripts/mcp_smoke_test.py
```
