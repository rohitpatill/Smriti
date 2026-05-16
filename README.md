# Smriti

A voice-driven second brain. You talk; Gemini Live listens, talks back, and silently maintains an Obsidian-compatible markdown vault of who you are and what you're up to. The vault is a flat folder of markdown files — open it in Obsidian to browse the graph of your own mind.

## How it works

```
Browser mic ──▶ WebSocket ──▶ Gemini Live (audio in / audio out)
                                    │
                                    ▼
                            graph_operation tool
                                    │
                                    ▼
                       Vault: identity.md + {id}.md nodes
                                    │
                                    ▼
                              Obsidian (you)
```

- `identity.md` — always-loaded snapshot of who you are and what's active right now.
- `{14-digit-id}.md` — every other entity (people, projects, events, concepts) as its own node, linked together via `[[id|Display]]`.
- The agent updates the graph naturally as you talk. You never edit it yourself.

## Setup

**Prerequisites**

- Python 3.11+
- A Gemini API key — get one at <https://aistudio.google.com>
- [Obsidian](https://obsidian.md) — to view the vault as a graph
  - Recommended plugin: **Front Matter Title** by Snezhig (enables the graph view to show node titles instead of numeric IDs)

**Install**

```bash
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```
GEMINI_API_KEY=your_key_here
VAULT_PATH=C:/path/to/your/ObsidianVault
```

`VAULT_PATH` is the folder Smriti will treat as your brain. Open the same folder in Obsidian to browse the graph live.

**Run**

```bash
python server.py
```

Open <http://localhost:8002>, click the mic, start talking.

## Project layout

- `server.py` — FastAPI + WebSocket, Gemini Live session, tool dispatch
- `index.html` — browser client (mic capture, audio playback, transcripts)
- `tools/graph_operation.py` — single action-flag tool over the vault
- `tools/time_context.py` — injects current Asia/Kolkata date/time awareness into the system prompt
- `config/system_instructions.md` — agent persona and rules
- `future_plans/` — designs deferred for later (e.g. compaction)
- `CLAUDE.md` — full developer guide for working inside this codebase
