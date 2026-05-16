# CLAUDE.md — Smriti Project Guide

This file orients Claude Code (or any agent) working inside the `Smriti/` directory. Read this before touching anything.

## What Smriti Is

Smriti is a voice-driven second-brain agent. The user speaks into a browser mic; audio streams to Gemini Live; Gemini responds in audio and, when needed, invokes a single tool — `graph_operation` — that reads and writes a vault of markdown files. Open that vault in Obsidian to browse the resulting knowledge graph.

The architecture deliberately separates three things:

1. **System** — code, system prompt, chat history. Lives in this codebase. Never written to the vault.
2. **Brain** — the user's actual knowledge. Lives in the configured vault folder (path from `.env`). Only markdown files written by `graph_operation`.
3. **Tool** — the single contract between (1) and (2). One function with action flags.

## Project Layout

```
Smriti/
├── server.py                       # Entry point: FastAPI + WebSocket + Gemini Live
├── index.html                      # Browser client: mic capture, audio playback, transcript UI
├── tools/
│   ├── __init__.py                 # Re-exports GraphOperation, execute, TOOL_DECLARATION
│   └── graph_operation.py          # The one tool. Handles every vault operation.
├── config/
│   └── system_instructions.md      # System prompt loaded into Gemini at session start
├── .env                            # GOOGLE_API_KEY / GEMINI_API_KEY, VAULT_PATH
├── .env.example                    # Template for .env
├── requirements.txt                # google-genai, fastapi, uvicorn, python-dotenv
├── README.md                       # User-facing quick start
└── CLAUDE.md                       # This file
```

## File-by-File Breakdown

### `server.py`

The orchestrator. On startup:

1. Loads `.env` and validates `GOOGLE_API_KEY` (or `GEMINI_API_KEY`) and `VAULT_PATH`.
2. Defines `build_system_prompt(graph)` which concatenates `config/system_instructions.md` with the current contents of `identity.md`. This composite prompt is the model's full system instruction — the user's working memory is always present.
3. Serves `index.html` at `GET /`.
4. Exposes a WebSocket at `/ws`.

On each `/ws` connection:

1. Instantiates a `GraphOperation(VAULT_PATH)`. The constructor auto-creates `identity.md` if missing.
2. Opens a Gemini Live session with:
   - `response_modalities=["AUDIO"]`
   - **Locked voice**: `Aoede` via `SpeechConfig(VoiceConfig(PrebuiltVoiceConfig(voice_name="Aoede")))`. Do not remove — without this, Gemini rotates voices randomly each session.
   - `system_instruction=build_system_prompt(graph)`
   - `tools=[Tool(function_declarations=[FunctionDeclaration(**TOOL_DECLARATION)])]`
   - `input_audio_transcription` and `output_audio_transcription` enabled
3. Runs two coroutines concurrently:
   - `browser_to_gemini`: decodes base64 PCM from the WS, forwards to `session.send_realtime_input(audio=Blob(mime_type="audio/pcm;rate=16000"))`.
   - `gemini_to_browser`: iterates `session.receive()`, forwarding audio chunks (base64-encoded 24kHz PCM), input/output transcriptions, turn_complete, interrupted, and **tool_call** events.

When a `tool_call` arrives, the server pops `action` out of `fc.args`, calls `execute(graph, action, **args)`, and replies via `session.send_tool_response`. The model sees the response and continues its turn.

Port: `127.0.0.1:8002`. Use `localhost` in the browser.

### `index.html`

Single-file browser client. No build step.

- **Mic capture**: `getUserMedia` at 16kHz mono, fed through an `AudioWorkletNode` that converts Float32 → Int16 PCM, base64-encodes, and sends as `{type: "audio", data: <base64>}` over WS.
- **Audio playback**: receives `{type: "audio", data: <base64>}` 24kHz Int16 PCM, decodes to Float32, queues into Web Audio API. The queue is barge-in safe: when an `interrupted` message arrives, the queue is cleared so the assistant stops mid-sentence.
- **Transcripts**: `input_transcript` (what the user said) and `output_transcript` (what Smriti said) accumulate into transcript bubbles. `turn_complete` resets the current bubbles.
- **Tool indicator**: small spinner labeled e.g. "Creating node…", "Updating identity…" when a tool call is in flight.

Style is dark, minimal, purple accent. Tab title is "Smriti — Your Second Brain".

### `tools/graph_operation.py`

The single tool. Class `GraphOperation` wraps the vault; module-level `execute(graph, action, **kwargs)` dispatches actions. `TOOL_DECLARATION` is the JSON schema fed to Gemini.

**Vault model**

- Vault is a flat folder of `.md` files.
- One special file: `identity.md` — the user's always-loaded working memory.
- Every other file is a **node**, named `{14-digit-id}.md` (e.g. `15900505552053.md`).
- Each node's YAML frontmatter:
  ```yaml
  id: 15900505552053          # the node's permanent identity
  title: GraphX               # human-readable name
  aliases:                    # YAML list — Obsidian uses this for graph labels
    - GraphX                  # (with Front Matter Title plugin enabled)
  type: project               # project | event | person | concept | goal | note | ...
  created: 2026-05-16
  updated: 2026-05-16
  ```

**Why filenames are pure IDs**

Obsidian resolves `[[15900505552053]]` by looking for a file literally named `15900505552053.md`. If the filename were `graphx-15900505552053.md`, Obsidian would treat the link as broken and silently create a phantom `15900505552053.md`. So filenames are IDs, and the title is surfaced via the `aliases:` frontmatter list (which the Front Matter Title community plugin renders in graph view, tabs, file explorer, etc.).

**Link format — strictly enforced**

All links are `[[<14-digit-id>|<Display Text>]]`. The validator `_validate_links()` runs inside `write_identity`, `create_node`, `update_node`, and `edit_node`. It rejects content that contains:

- Any `[[xxx|...]]` where `xxx` is not exactly 14 digits.
- Any `[[14digitid|...]]` where the ID doesn't correspond to an existing node file.

A rejected call returns `{"status": "error", "error": "...", "link_errors": [...]}` so the model can fix and retry.

**Actions exposed via `execute(graph, action, **kwargs)`**

| Action | Required args | What it does |
|---|---|---|
| `read_identity` | — | Read `identity.md`, return content + extracted links |
| `write_identity` | `content` | Overwrite `identity.md`. Preserves/refreshes frontmatter. Validates links. |
| `read_node` | `node_id` | Read a node by ID. Returns content, parsed metadata, extracted links. |
| `create_node` | `title`, `type`, optional `content` | Generate a new 14-digit ID (collision-checked), write `{id}.md` with full frontmatter including `aliases: [title]`. Returns the ID. |
| `update_node` | `node_id`, `content` | Overwrite a node's content. Bumps `updated`. Keeps `id`. Syncs `aliases` to current `title`. Validates links. |
| `edit_node` | `node_id`, `old_string`, `new_string`, optional `replace_all` | Precise text replacement. Validates resulting links. |
| `list_nodes` | — | List every node with id/title/type/updated. |
| `extract_links` | `content` | Parse `[[id\|display]]` from arbitrary content; returns `[{id, display}, ...]`. |
| `delete_node` | `node_id` | Delete the file, return backup content. |

**IDs**

- 14 numeric digits, generated by `secrets.choice("0123456789")` in `_new_id()`.
- Collision-checked against `{vault}/{id}.md` before use.
- The agent must NEVER invent an ID. It only ever uses the ID returned by a prior `create_node` call.

**Frontmatter parser**

`_parse_frontmatter()` handles scalar fields (`key: value`), inline lists (`key: [a, b, c]`), and multi-line YAML lists (`key:\n  - a\n  - b`). `_build_frontmatter()` writes lists back in multi-line form so `aliases:` round-trips cleanly.

### `config/system_instructions.md`

The system prompt. Loaded by `build_system_prompt()` every time `/ws` opens and again whenever the model reads `identity.md`. Contains:

1. The agent's persona — quiet, curious, friend-like; explicitly forbids announcements like "I've created a node" or "I've updated your identity".
2. Vault and node schema definitions.
3. Hard rules about link format with ✅ / ❌ examples — the most important section, because Gemini will otherwise hallucinate plausible-looking link targets like `[[project-id|GraphX]]`.
4. Workflow: listen, reply naturally, silently maintain the graph.

Do NOT relax the "no announcements" rules or the link format rules without thinking through the consequences — the model regresses to bad behavior fast.

### `.env` and `.env.example`

Required keys:

```
GOOGLE_API_KEY=...        # or GEMINI_API_KEY; server.py accepts either
VAULT_PATH=C:/path/to/ObsidianVault
```

`VAULT_PATH` is the folder the agent treats as the user's brain. Point Obsidian at the same folder so the user can browse the graph.

### `requirements.txt`

```
google-genai>=1.68.0
fastapi
uvicorn[standard]
python-dotenv
```

No build tooling, no Node, no compiler. `pip install -r requirements.txt` and `python server.py` is the entire install.

## Runtime Flow

```
User speaks
  │
  ▼
Browser AudioWorklet → 16kHz Int16 PCM → base64 → WebSocket
  │
  ▼
server.py (browser_to_gemini coroutine)
  │
  ▼
Gemini Live session (model="gemini-3.1-flash-live-preview", voice="Aoede")
  │
  ├── system_instruction = config/system_instructions.md + current identity.md
  ├── tools = [graph_operation]
  │
  ▼
Model decides:
  ├── Reply with audio                            → gemini_to_browser → WS → browser plays
  ├── Need to update identity / create node / etc → tool_call
  │                                                   │
  │                                                   ▼
  │                                          server.py executes action
  │                                                   │
  │                                                   ▼
  │                                          GraphOperation writes to vault
  │                                                   │
  │                                                   ▼
  │                                          send_tool_response → model continues
  ▼
Continue until turn_complete
```

## Conventions When Modifying This Project

- **Don't add folders inside the vault.** The vault is flat by design — one level, IDs as filenames. Anything else breaks Obsidian's resolver and the link validator.
- **Don't add more tools.** `graph_operation` with action flags is the contract. More tools = more model confusion. Add a new action to the existing tool instead.
- **Don't write conversation logs or system state to the vault.** The vault is the user's brain content only. Chat history lives in memory or in this codebase if needed.
- **Don't let the model invent IDs.** Every write that introduces a link must use an ID returned by a real `create_node` call. The server-side validator enforces this; don't disable it.
- **Don't change the voice without telling the user.** It's pinned to `Aoede` because the user explicitly asked for a stable voice.
- **When editing `system_instructions.md`**: changes here propagate on the next WebSocket connection. No restart needed unless `server.py` itself changed.
- **When editing `graph_operation.py` or `server.py`**: restart `python server.py`.

## Known Sharp Edges

- **Obsidian graph labels show the filename (the ID) by default.** Install the community plugin **"Front Matter Title"** by Snezhig, enable its "Graph" feature, and set the title field to `title`. Frontmatter already has both `title:` and `aliases:` to feed it.
- **Identity.md must stay tight.** Target under ~10,000 chars. Detail belongs in nodes, not in identity. The system prompt enforces this but it's worth watching during long sessions.
- **`_parse_frontmatter` is hand-rolled** (not PyYAML) to avoid a dep. It supports the subset the agent actually writes (scalars + flat lists). If you add nested structures, switch to PyYAML.
- **Validator scans the whole vault** on every write to build the set of existing IDs. Fine for thousands of nodes; if the vault grows huge, cache it on the `GraphOperation` instance.

## Quick Commands

```bash
# install
pip install -r requirements.txt

# run
python server.py
# → opens on http://localhost:8002

# smoke test the tool without the server
python -c "from tools import GraphOperation, execute; g = GraphOperation('C:/tmp/test_vault'); print(execute(g, 'list_nodes'))"
```
