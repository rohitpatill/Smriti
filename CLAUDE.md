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
├── index.html                      # Browser client: mic capture, audio playback, transcripts
├── tools/
│   ├── __init__.py                 # Re-exports GraphOperation, execute, TOOL_DECLARATION, build_time_context
│   ├── graph_operation.py          # The one tool. Handles every vault operation.
│   └── time_context.py             # Builds the Asia/Kolkata time-awareness block injected into the system prompt
├── config/
│   └── system_instructions.md      # System prompt — persona, link rules, decay logic, replica behavior, etc.
├── future_plans/
│   └── context_management.md       # Deferred design: three-prompt compaction, server-side buffer, logging
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
2. Defines `build_system_prompt(graph)` which concatenates:
   - `config/system_instructions.md`
   - `build_time_context()` — fresh Asia/Kolkata time block (today/yesterday/tomorrow, last 7 / next 7 day enumeration, last/next month range, current time + part of day)
   - The current contents of `identity.md`
   This composite is the model's full system instruction — working memory is always present and dates are always current.
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
  description: One-to-three   # short gist surfaced by list_nodes peeks
    line summary
  type:                       # NORMALIZED lowercase list — supports multiple
    - project
    - work
  created: 2026-05-16
  updated: 2026-05-16
  ```

**Why filenames are pure IDs**

Obsidian resolves `[[15900505552053]]` by looking for a file literally named `15900505552053.md`. If the filename were `graphx-15900505552053.md`, Obsidian would treat the link as broken and silently create a phantom `15900505552053.md`. So filenames are IDs, and the title is surfaced via the `aliases:` frontmatter list (which the Front Matter Title community plugin renders in graph view, tabs, file explorer, etc.).

**Description field**

Every node has a 1-3 line `description:` in frontmatter. It's the *gist* — what someone needs to recall this entity at a glance. The agent must keep it current. Surfaced by `list_nodes` peeks so the agent can scan neighbors cheaply (id + title + type + description) before deciding which to drill into.

**Type as a normalized list**

`type` is always a list. A person can be `[friend, colleague]`. The agent can pass any reasonable spelling — `"Friend, Co-Worker"` or `["Friend", "co-worker"]` — and the server normalizes (lowercase, spaces → hyphens, dedupes order-preserving). This enables filtering: `list_nodes(node_id=..., type="friend")` returns only friend-typed neighbors.

**Auto-timestamping on writes**

Every line that is *added or modified* in `identity.md`, `update_node`, or `edit_node` gets `<!-- YYYY-MM-DD HH:MM -->` (Asia/Kolkata) appended automatically by the server. The agent does NOT write these markers; it just writes content. Unchanged lines keep their old stamps (computed via `difflib.SequenceMatcher` on stamp-stripped content) — this is what makes the stamp mean "last reinforced." The agent reads stamps to reason about age and decay.

Heading lines (`#`, `##`, …), blank lines, code fences, and frontmatter delimiters are never stamped. `create_node` also stamps its initial body so every line has a baseline age.

**Link format — strictly enforced**

All links are `[[<14-digit-id>|<Display Text>]]`. The validator `_validate_links()` runs inside `write_identity`, `create_node`, `update_node`, and `edit_node`. It rejects content that contains:

- Any `[[xxx|...]]` where `xxx` is not exactly 14 digits.
- Any `[[14digitid|...]]` where the ID doesn't correspond to an existing node file.

A rejected call returns `{"status": "error", "error": "...", "link_errors": [...]}` so the model can fix and retry.

**ID cache for the validator**

`GraphOperation` keeps a `_id_cache: set[str]` of existing node IDs. Built lazily on first use (single `glob` pass), invalidated on `create_node` / `delete_node`. Lookup is O(1) thereafter — no full vault scan per write.

**Actions exposed via `execute(graph, action, **kwargs)`**

| Action | Required args | What it does |
|---|---|---|
| `read_identity` | — | Read `identity.md`, return content + extracted links |
| `write_identity` | `content` | Overwrite `identity.md`. Preserves frontmatter, refreshes `updated`. Validates links. Auto-stamps modified body lines. |
| `read_node` | `node_id` | Read a node by ID. Returns content, parsed metadata, `description`, `type`, extracted links. |
| `create_node` | `title`, `type`, optional `content`, optional `description` | Generate a new 14-digit ID (collision-checked against cache), write `{id}.md` with full frontmatter including `aliases: [title]`, normalized `type` list, `description`. Initial body lines are stamped. Returns the ID. |
| `update_node` | `node_id`, `content`, optional `description` | Overwrite a node's content. Merges frontmatter, bumps `updated`, keeps `id`, syncs `aliases` to current `title`, re-normalizes `type`. Validates links. Auto-stamps modified body lines. |
| `edit_node` | `node_id`, `old_string`, `new_string`, optional `replace_all` | Precise text replacement. Validates resulting links. Auto-stamps modified body lines. |
| `list_nodes` | optional `node_id`, optional `type` | **Neighbor traversal**, not a flat dump. Walks `[[...]]` links of one source node (defaults to `identity.md`) and returns peeks `{id, title, type, description, updated}` for each. Optional `type` filters to neighbors with that type. Never globs the vault. |
| `extract_links` | `content` | Parse `[[id\|display]]` from arbitrary content; returns `[{id, display}, ...]`. |
| `delete_node` | `node_id` | Delete the file, return backup content. Invalidates ID cache. |

**IDs**

- 14 numeric digits, generated by `secrets.choice("0123456789")` in `_new_id()`.
- Collision-checked against the ID cache and `{vault}/{id}.md` before use.
- The agent must NEVER invent an ID. It only ever uses the ID returned by a prior `create_node` call.

**Frontmatter parser**

`_parse_frontmatter()` handles scalar fields (`key: value`), inline lists (`key: [a, b, c]`), and multi-line YAML lists (`key:\n  - a\n  - b`). `_build_frontmatter()` writes lists back in multi-line form so `aliases:` and `type:` round-trip cleanly.

### `tools/time_context.py`

Builds the Asia/Kolkata time-awareness block injected into the system prompt at every WebSocket connect. Includes:

- Now (date, time, weekday, part of day)
- Today / yesterday / day-before / tomorrow / day-after as absolute dates
- Full enumeration of the last 7 and next 7 days with weekday names
- Last/next month range

The agent never has to do date arithmetic — it just reads the block. Part-of-day classifications (`morning`, `midday`, `evening`, `late evening`, `late night`) color the agent's tone naturally.

### `config/system_instructions.md`

The system prompt. Loaded by `build_system_prompt()` every time `/ws` opens. The full rewrite covers:

1. **Persona** — quiet, curious, friend-like; explicitly forbids announcements ("I've created a node", "I've updated your identity").
2. **Replica behavior** — the agent observes the user's phrasing, language mix, humor, emotional tone, and gradually mirrors them. Core Identity in `identity.md` is allowed to grow as the replica deepens.
3. **Backbone** — agent has its own perspective; pushes back gently when the user is wrong; not a yes-machine.
4. **Vault schema** — node frontmatter (id, title, aliases, description, type list, created, updated).
5. **Link discipline** — `[[14digitid|Display]]` rules with ✅/❌ examples. Most important section; Gemini regresses to bad behavior fast without it.
6. **identity.md structure** — five sections, top to bottom, stable → frequent:
   - Core Identity (stable, can grow with personality observations)
   - People (close circle, concise links; inner ~5 never decay)
   - Life Phase (slow-changing)
   - Events (live; absolute dates only; decays ~2 weeks past event)
   - Active Focus (live, detailed, decays in 2-3 days without mention)
7. **Auto-linking** — when mentioning an entity inside a node, the agent must link it (`[[id|Name]]`) not write plain text. Lookup strategy: identity.md → current node neighbors → ask user → create.
8. **Decay = relocation** — information is never deleted; demoted from identity.md to a properly-linked node first, only then removed from the flash.
9. **Time awareness** — relative speech ("tomorrow") is fine in conversation; writes must resolve to absolute dates. Greetings adapt to part of day. Contradictions trigger human curiosity, not silent overwrites.
10. **Tool discipline** — never invent IDs, prefer `edit_node` for small changes, always include `description` on `create_node`, fix and retry on `link_errors`.

Do NOT relax the "no announcements" rules or the link format rules without thinking through the consequences — the model regresses to bad behavior fast.

### `future_plans/context_management.md`

Captures the deferred three-prompt compaction design we discussed but couldn't implement because Gemini Live manages session history server-side and exposes no manipulation API. Documents:

- The pre-compaction alert / compaction / post-compaction-notice flow
- Configuration shape (`COMPACTION_THRESHOLD_TOKENS`, `COMPACTION_PRE_ALERT_PERCENT`, etc.)
- Required server-side conversation buffer
- UI hook events (`compaction_alert`, `compaction_start`, `compaction_complete`, `pause_input`, `resume_input`)
- Logging plan (`logs/{timestamp}_session.log`, async fire-and-forget)
- The API constraint that blocks all of the above

Revisit when a different voice API exposes manipulable history or when we switch to a self-managed STT → LLM → TTS pipeline.

### `.env` and `.env.example`

Required keys:

```
GOOGLE_API_KEY=...                  # or GEMINI_API_KEY; server.py accepts either
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
  ├── system_instruction = config/system_instructions.md
  │                        + time_context (Asia/Kolkata)
  │                        + current identity.md
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
  │                                          (auto-stamps modified lines,
  │                                          validates links via cached ID set)
  │                                                   │
  │                                                   ▼
  │                                          send_tool_response → model continues
  ▼
Continue until turn_complete, then loop until WS closes
```

## Conventions When Modifying This Project

- **Don't add folders inside the vault.** The vault is flat by design — one level, IDs as filenames. Anything else breaks Obsidian's resolver and the link validator.
- **Don't add more tools.** `graph_operation` with action flags is the contract. More tools = more model confusion. Add a new action to the existing tool instead.
- **Don't expose a flat full-vault listing.** `list_nodes` is intentionally neighbor-traversal only. As the vault scales to thousands of nodes, dumping everything would explode the context window.
- **Don't write conversation logs or system state to the vault.** The vault is the user's brain content only. Chat history lives in memory (or in `logs/` if we ever add the logging plan from `future_plans/`).
- **Don't let the model invent IDs.** Every write that introduces a link must use an ID returned by a real `create_node` call. The server-side validator enforces this; don't disable it.
- **Don't have the model write `<!-- date -->` stamps manually.** The server appends them automatically on modified lines. If you change this, update the system prompt section that tells the model not to write stamps.
- **Don't change the voice without telling the user.** It's pinned to `Aoede` because the user explicitly asked for a stable voice.
- **Don't change the timezone.** It's pinned to `Asia/Kolkata` for time context, greetings, and stamps.
- **When editing `system_instructions.md`**: changes propagate on the next WebSocket connection. No restart needed unless `server.py` itself changed.
- **When editing `graph_operation.py`, `time_context.py`, or `server.py`**: restart `python server.py`.

## Known Sharp Edges

- **Obsidian graph labels show the filename (the ID) by default.** Install the community plugin **"Front Matter Title"** by Snezhig, enable its "Graph" feature, and set the title field to `title`. Frontmatter already has both `title:` and `aliases:` to feed it.
- **Identity.md target size.** The user is fine with up to ~50k characters; we don't cap it. Just keep detail in nodes when it belongs there, not in the flash.
- **`_parse_frontmatter` is hand-rolled** (not PyYAML) to avoid a dep. It supports the subset the agent actually writes (scalars + flat lists, inline or multi-line). If you add nested structures, switch to PyYAML.
- **Validator ID cache is per-`GraphOperation` instance.** A fresh instance is created per WebSocket connection (server-side). Cross-process edits to the vault folder won't be seen until the next connect — fine for the current single-server setup.
- **Voice-mode history is owned by Google.** We can read `usage_metadata` but cannot read, prune, summarize, or replay the session. Hence the threshold reminder approach; full compaction is parked in `future_plans/`.

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
