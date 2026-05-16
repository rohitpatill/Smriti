# Smriti

Voice-driven second-brain agent. Browser mic → Gemini Live → `graph_operation` tool → markdown vault. Open the same vault in Obsidian to browse the graph.

## Setup

```bash
cp .env.example .env
# Edit .env: set GEMINI_API_KEY (or GOOGLE_API_KEY) and VAULT_PATH
pip install -r requirements.txt
python server.py
# Open http://localhost:8002
```

## Layout

- `server.py` — FastAPI + WebSocket, Gemini Live session, tool dispatch
- `index.html` — browser client (mic capture, audio playback, transcripts)
- `tools/graph_operation.py` — single action-flag tool over the vault
- `config/system_instructions.md` — system prompt (never written to vault)
- `.env` — `GEMINI_API_KEY`, `VAULT_PATH`

## Vault

Whatever path you put in `VAULT_PATH` becomes the brain. `identity.md` is auto-created on first connect. Every other file is `{14-digit-id}.md`. Links use `[[id|Display]]` so node references survive renames and name collisions.
