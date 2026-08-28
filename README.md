# ReBOB — Memory for IBM Bob

ReBOB gives [IBM Bob](https://www.ibm.com/products/watson) persistent memory across conversations.
It captures, indexes, and retrieves context so Bob can remember what matters.

## Quick start

```bash
pip install -r requirements.txt
```

## Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

> **Status:** early scaffolding — stub implementations only.

## Phase 1 — MCP setup

### Test locally

```bash
pip install -r requirements.txt
python rebob/server.py        # starts stdio server; creates .rebob/rebob.db
```

### Connect Bob (Person B)

1. Copy `rebob/mcp.example.json` → `.bob/mcp.json`
2. Replace `<ABSOLUTE_PATH>` with the absolute path to this repo root
3. In Bob Settings → MCP, enable **"MCP tools for new tasks"**
4. Start a new Bob task and ask: `call mem_search with query="test"`
