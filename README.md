# Smriti

> *A second brain that doesn't store what you know — it remembers who you are.*

Smriti is a voice-first agent that quietly maintains a living model of you. You talk to it like a friend; it listens, responds, and silently rewires a markdown graph in the background — a graph that, over time, becomes the closest thing to a digital snapshot of your awakening mind.

The vault sits in a plain folder. Open it in [Obsidian](https://obsidian.md) and you'll see the shape of your own life: the people closest to you, the projects you're inside of right now, the events on the horizon, the threads you're chasing this week — all linked, all dated, all evolving as you keep talking.

You never edit a file. You just speak.


<img width="1448" height="1086" alt="image" src="https://github.com/user-attachments/assets/fb11a406-e417-4a65-94c7-fc81652565ed" />


---

## The Idea — Where This Came From

### The seed

The starting spark was the **LLM Wiki pattern** that Andrej Karpathy popularised in early 2025 — the realisation that an LLM, given a folder of markdown files, doesn't need to be told to *retrieve* knowledge; it can be told to *compile and maintain* it. Obsidian becomes the IDE, the LLM becomes the programmer, the markdown vault becomes the codebase. Knowledge compounds instead of being re-derived on every query.

That pattern is powerful for documents — research notes, book companions, competitive analysis, anything where you're accumulating *external* information.

Smriti applies the same shape to a different problem: **not what you've read, but who you are.**

### The shift — from a wiki of documents to a snapshot of a person

A document wiki has two layers: raw sources you drop in, and a compiled wiki the LLM maintains from them. Smriti has no sources layer. There's nothing being "ingested." The raw input is **you, in conversation** — the way a friend's understanding of you accumulates not from reading files about you, but from years of talking.

So instead of `sources/` and `wiki/`, Smriti has one thing: a vault that represents your mind at this moment. And at the centre of that vault is one special file — `identity.md` — that we built around a very specific metaphor.

### The awakening-state metaphor

If someone woke you up at 3 a.m. and asked *"who are you, what's going on in your life right now?"* — what would your brain hand back?

Not a search index. Not a list of documents. A **layered snapshot**, top to bottom in roughly this order:

1. **Core identity** — your name, where you're from, where you grew up, your family, the formative chapters of your life, the way you think, the people closest to you. Stuff that's been true for years and will still be true years from now. Permanent. Stable.
2. **Life phase** — what chapter you're in *right now*. The job, the city, the degree you're finishing, the relationship you just entered. Slow-changing, but it does change. A new job moves this whole section.
3. **Events** — what's on the horizon or what just happened. The trip in two weeks, the demo on Thursday, the wedding last Saturday. Lives for a few weeks, then decays.
4. **Active focus** — what you're actually inside of *this week, today, this hour*. The bug you're debugging. The chapter you're writing. The conversation you can't stop thinking about. Decays in days.

Your brain doesn't load all of your life every time you wake up. It loads exactly this stack — stable at the top, fluid at the bottom. **That's identity.md.** A single markdown file, always in the agent's context, structured exactly along those layers, refreshed continuously as you talk.

If you'd woken up the same brain ten years ago, the core would be similar (same parents, same hometown), but the phase, events, and focus would have been totally different — different school, different exams, different friends in rotation. The file's *structure* is permanent; its *contents* shift as life shifts.

### Why timestamps on every line

If the brain is a snapshot, the agent needs to know **how old each piece of the snapshot is**. Otherwise a focus item from three weeks ago will sit there pretending to be current.

Every line written to the vault is automatically stamped with `<!-- YYYY-MM-DD HH:MM -->` (Asia/Kolkata). Lines that didn't change on a write keep their original stamp — which is what makes the stamp mean *"last reinforced,"* not *"last touched."* When you mention something again, even identically, its line gets rewritten and the stamp refreshes. When you don't mention something for days, its stamp ages and the agent can see it's gone cold.

This is how decay works. Active Focus items that haven't been refreshed in 2–3 days drop out of identity.md. Events that are two weeks past their date drop out. The information isn't deleted — it's **demoted** into deeper nodes, still linked from somewhere, still reachable. The flash just gets quieter as things naturally fade.

### Why everything else is a 14-digit ID

Outside identity.md, every entity in your life is a separate markdown file: a person, a project, a place, a recurring activity, a book you're reading, an event. Each one named by a flat 14-digit number — `15900505552053.md`, `64756843108938.md` — and linked from anywhere it's mentioned using Obsidian's `[[id|Display Name]]` syntax.

Numeric IDs aren't a quirk; they're load-bearing:

- **Identity is permanent.** If a person's title changes (nickname, marriage, role), their *file* doesn't have to move or rename. The ID is stable; the title is metadata. Links never break.
- **No filename clashes.** Two friends named Aditya don't collide. Two projects with similar names don't collide.
- **The graph is the brain.** Each node is a neuron. Each `[[id|...]]` link is a synapse. Obsidian's graph view literally shows you the shape of your mind — what's at the centre, what's at the edge, what's connected to what.

Whether something belongs in identity.md or deep in the graph is determined by **inbound links**, not by file location. Promoting a node into working memory means adding a link to it from identity.md. Demoting it means removing that link. The file never moves; only the synapse pattern changes. Same as the brain — neurons don't migrate; their connection strength does.

### Why one tool

The agent has exactly one tool, `graph_operation`, with eleven actions (`read_identity`, `create_node`, `find_node`, `update_node`, `edit_node`, `search_content`, …). Not eleven separate tools — one tool, one mental contract.

The reason is discipline. The fewer tools an LLM has, the less time it spends choosing between them and the more time it spends thinking about *content*. Every action funnels through the same dispatcher, the same link validator, the same auto-stamping logic. A new operation isn't a new tool — it's a new action on the same one. The model never has to learn a new surface.

### Voice-first, not chat-first

Smriti is built around speech, not typing. Two reasons:

1. **You talk about your life the way you live it** — in half-sentences, in fragments, in the way friends actually talk. Typing forces structure that kills the natural flow of self-reflection.
2. **The agent should feel like a person, not a notebook.** Voice closes that gap in a way text never quite does. A late-night ramble into a microphone behaves very differently in your brain than a late-night journal entry.

The browser client streams microphone audio to a Gemini Live session, which streams audio back. Transcripts are shown live but the conversation itself is voice. The agent uses Asia/Kolkata time awareness to colour its tone — *"midnight, what's keeping you up?"* in the early hours, *"morning, how'd you sleep?"* after dawn.

### One file at the centre, one graph around it, one voice between you and it

That's the whole shape:

- **identity.md** — your awakening-state snapshot. Always loaded into the agent's context. The thing it reads to know who you are right now.
- **The graph** — every person, project, event, idea, place as its own 14-digit-ID node, linked together. The deep history.
- **The agent** — quietly maintaining both, refreshing what's warm, decaying what's cold, never narrating the bookkeeping. Just talking to you.

---

## How It Works In Practice

```
You speak
    │
    ▼
Browser mic ──▶ WebSocket ──▶ Gemini Live (audio in / audio out)
                                    │
                                    ▼
                            graph_operation tool
                                    │
                                    ▼
                       Vault: identity.md + {id}.md nodes
                                    │
                                    ▼
                          Obsidian — you, browsing
```

Or, equivalently, through any MCP-aware client:

```
Claude Desktop / Cursor / Claude Code
            │  (stdio)
            ▼
        mcp_server.py
            │
            ▼
    Same vault, same graph
```

Both interfaces drive the same tool, the same vault, the same brain. Use whichever you prefer — talk to it through Gemini Live in the browser, or chat with it through any local MCP client. The vault doesn't care.

### What the agent does each turn

1. **Listens** — picks up not just what you said, but the emotional register, the people you mentioned, the things you trailed off from.
2. **Responds** — like a friend, in your rhythm, sometimes pushing back when you're being unfair to yourself or someone else. It's not a yes-machine.
3. **Silently rewires the graph**:
   - New person mentioned? `find_node` first (to avoid duplicates), then `create_node` if genuinely new, then link them into the right parent (identity.md's People, a workplace node, wherever they belong).
   - Existing entity reinforced? Rewrite their line so the timestamp refreshes. Drop any new detail into *their* node body, not the parent.
   - Focus shifted? Promote the new thing to Active Focus; demote what went cold.
   - Personality pattern noticed? Add it to Core Identity.
4. **Evolves** — every turn, silently re-evaluates whether the graph's current shape still reflects reality. A colleague who's become a close friend gets their type updated and gets promoted into identity.md's People section. A side project that's become the main thing gets surfaced into Active Focus. A trip that's two weeks past its date quietly leaves the live tracker.

You never see any of this happen. You just talk.

---

## The Vault — What You'll See In Obsidian

```
your-vault/
├── identity.md                  # The always-loaded snapshot of you
├── 15900505552053.md            # A project
├── 64756843108938.md            # A friend
├── 71203984561200.md            # A workplace
├── 98913218537853.md            # An event
└── …                            # Everything else, one node per entity
```

Open the vault folder in Obsidian, turn on graph view, and you'll see identity.md at the centre with everything else radiating outward — the people closest to you one hop away, their contexts two hops away, the rabbit holes deeper still.

**Recommended plugin: [Front Matter Title](https://github.com/Snezhig/obsidian-front-matter-title) by Snezhig.** Without it Obsidian labels nodes by their filename (the raw 14-digit ID). With it, graph view shows the actual names — *Aditya*, *GraphX*, *Goa Trip 2026* — pulled from each file's `aliases:` frontmatter.

---

## Setup

### Prerequisites

- **Python 3.11+**
- **Obsidian** ([download](https://obsidian.md)) — the front-end for browsing your vault. Cross-platform; pick the build for your OS.
  - Install the **Front Matter Title** community plugin (Settings → Community plugins → Browse → search "Front Matter Title" → install + enable; in its settings, enable the *Graph* feature).
- **A vault folder** anywhere on your machine. Anything — `Documents/SmritiVault`, `D:/brain`, `~/obsidian/me`. Just an empty folder. Smriti will populate it.
- **A Gemini API key** ([get one at AI Studio](https://aistudio.google.com)) — only required if you want the voice interface. The MCP interface doesn't need it.

### Install

```bash
git clone <this-repo>
cd Smriti
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```
GEMINI_API_KEY=your_key_here          # only needed for voice mode
VAULT_PATH=C:/path/to/your/vault      # any folder; will be auto-populated
```

> On macOS / Linux use forward slashes too: `VAULT_PATH=/Users/you/SmritiVault`.

Then open the same folder in Obsidian (`Open folder as vault`) so you can browse the graph live as it builds.

---

## Running Smriti

There are two ways to talk to your brain. Use either, or both — they share the vault.

### 1. Voice mode (Gemini Live, browser)

The original interface. You speak into your laptop mic and Smriti speaks back.

```bash
python server.py
```

Then open <http://localhost:8002> in any modern browser, click the mic, and start talking. The voice is locked to *Aoede*; the timezone is locked to Asia/Kolkata. Talk in any language you like — English, Hindi, Hinglish, whatever's natural — but the graph itself is always written in English so it stays searchable.

### 2. MCP mode (any local LLM client)

If you'd rather talk to Smriti through Claude Desktop, Cursor, Claude Code, Continue, or any other MCP-aware client, point that client at `mcp_server.py`. No Gemini key required.

Add this to your client's MCP config (e.g. `~/.cursor/mcp.json`, Claude Desktop's `claude_desktop_config.json`, or any client's equivalent):

```json
{
  "mcpServers": {
    "smriti": {
      "command": "python",
      "args": [
        "D:/Study/Smriti/mcp_server.py"
      ]
    }
  }
}
```

Adjust the path to wherever you cloned the repo. Restart the client. Smriti will appear as a tool provider with three tools: `get_system_instructions` (mandatory first call — it hands the LLM the full operating manual), `graph_operation`, and `get_time_context`.

Both interfaces are completely independent — you can run them simultaneously against the same vault, or run only one.

---

## Project Layout

```
Smriti/
├── server.py                    # Voice entry point — FastAPI + WebSocket + Gemini Live
├── mcp_server.py                # MCP entry point — stdio server for local LLM clients
├── index.html                   # Browser client (mic capture, audio playback, transcripts)
├── tools/
│   ├── graph_operation.py       # The one tool. All eleven actions live here.
│   └── time_context.py          # Asia/Kolkata time-awareness block
├── config/
│   └── system_instructions.md   # The agent's persona and operating contract
├── future_plans/                # Designs deferred for later (e.g. context compaction)
├── CLAUDE.md                    # Full developer guide for working inside this codebase
└── README.md                    # This file
```

For developers wanting to extend Smriti — add a new action, change the persona, plug in a different model — `CLAUDE.md` is the in-depth tour of every file.

---

## A Note On What This Isn't

Smriti is not a note-taking app. It's not a journaling tool. It's not RAG. It's not a chatbot with memory bolted on.

It's an attempt to model the way a brain actually *holds* a person — a stable core, a current chapter, a live horizon, an active focus — and to keep that model continuously up to date through conversation alone. The markdown vault is just the substrate. The real artefact is the snapshot the agent carries of you, which deepens with every conversation and decays with neglect, the way your own memory does.

Whether that's useful to you depends on what you want from a "second brain." If you want a knowledge base of documents, the Karpathy LLM-Wiki pattern is the right shape and there are several fine implementations of it. If you want something that knows *you* — your people, your phase, your week, your hour — that's what Smriti is for.
