# JK Assistance MCP server (admissions)

Lets Claude Desktop, Claude Code or any MCP client check a student's admission eligibility for AJK programs, explain the entry tests (MDCAT out of 180, ECAT out of 400), and walk them through applying.

## Run

For stdio:

```bash
python mcp_server/server.py
```

For Streamable HTTP at `http://localhost:8765/mcp`:

```bash
python mcp_server/server.py --http
```

## Configure

```json
{"mcpServers": {"jk-assistance": {"command": "python",
  "args": ["C:\\Users\\Faisal Ramzan\\Desktop\\AJK university VA\\mcp_server\\server.py"],
  "env": {"JK_DISABLE_LLM": "1"}}}}
```

Put this in Claude Code's `.mcp.json` or Claude Desktop's `%APPDATA%\Claude\claude_desktop_config.json`. Use the full path to the Python that has `requirements.txt` installed if `python` isn't on PATH.

## Tools

| Tool | Purpose |
|---|---|
| `check_admission` | Eligible programs with checklists (needed vs obtained), MBBS/BDS merit aggregate, chance, fees, how to apply |
| `get_test` | Max/min marks, format, fee, dates, merit formula (`mdcat`, `ecat`, `uajk_entry_test`, `must_seet`, `hec_lat`) |
| `how_to_apply` | Steps, documents, contacts, dates (`uajk`, `must`, `jac`) |
| `admission_dates` | Upcoming and recent admission dates, plus rules |
| `list_programs` | Program catalog |
| `search_admission_sources` | Evidence from the official sources |
| `ask_jk_assistance` | Full assistant for a free-text question |

Example prompt: *"Using jk-assistance: I did FSc pre-medical 946/1100, matric 1010/1100 and got 140 in MDCAT. Where can I apply and what do I do next?"*

## Smoke test

```bash
python scripts/mcp_smoke_test.py
```
