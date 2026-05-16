# Future Plan: Context Management & Compaction

Captured plans that we discussed but **deferred** because the current Gemini
Live API doesn't support the necessary primitives. Revisit when:

- A different voice API exposes manipulable session history, OR
- Gemini Live adds prompt caching / session export / mid-session history rewrite, OR
- We switch to a self-managed pipeline (STT → text LLM → TTS) where we own
  the full chat history client-side.

---

## The Constraint That Blocked Us

Gemini Live (`gemini-3.1-flash-live-preview`) is **stateful on Google's side**:

- We open a WebSocket session; Google maintains the conversation history.
- We cannot read, modify, summarize, cache, or reset the in-session history.
- The only "reset" is closing the socket — which loses *everything*.
- We only see `usage_metadata.total_token_count` after each `turn_complete`.

So none of the compaction logic below is implementable today. We track
tokens and nudge the user to start fresh when nearing the threshold — that's
the v1 we shipped.

---

## What We Designed (For Later)

### Three-Prompt Compaction Flow

| # | When | Purpose | Contents |
|---|------|---------|----------|
| 1. Pre-compaction alert | Tokens cross `THRESHOLD * (1 - PRE_ALERT_PCT)` | Silent nudge to model: capture any unsaved important info into the graph before compaction hits. | "You're approaching context limit. Quietly make sure all important info from this conversation is captured in the graph. Don't mention this to the user." |
| 2. Compaction prompt | Tokens cross `THRESHOLD` | Sent to a text-mode model alongside full session history, produces dense structured summary. | "Summarize this conversation: topics, decisions, node IDs touched, open threads, emotional context. Be dense, lose no important detail." |
| 3. Post-compaction notice | New session after compaction | Tells the resumed agent that its history is now a summary; behave as if conversation continued. | "The conversation summary above covers earlier turns. Continue naturally. Don't mention compaction. Check the graph if user references something not in the summary." |

### Flow

```
Turn N:
  - Read usage_metadata.total_token_count
  - If > PRE_ALERT and not yet alerted → inject Prompt #1 silently
  - If > THRESHOLD:
      a. UI shows "compacting…" spinner; pause mic input
      b. Collect conversation history (we'd need to track this ourselves)
      c. Call text endpoint with Prompt #2 + history → dense summary
      d. Close current Live session
      e. Open new Live session with:
           system_prompt + identity.md + time + Prompt #3 + summary
      f. Hide spinner; resume mic
  - Else: continue normally
```

### Configuration (`.env`)

```
COMPACTION_THRESHOLD_TOKENS=65000
COMPACTION_PRE_ALERT_PERCENT=10        # alert when 90% of threshold reached
COMPACTION_TARGET_TOKENS=4000          # target summary size
COMPACTION_TEXT_MODEL=gemini-3.1-flash-lite
```

### Compaction Summary Structure (suggested)

```
## Topics discussed
- ...

## Decisions / state changes
- Created node [[id|Title]] for X
- Updated identity Active Focus to Y

## Open threads (user may bring up again)
- ...

## Emotional context
- User was frustrated about X
- Excited about Y
```

Structured > prose: fewer tokens, easier for the resumed agent to scan.

---

## Server-Side Conversation Buffer (also blocked)

To compact, we'd need to maintain our own transcript log of the live session
since Google doesn't let us read theirs. That's straightforward:

- On every `input_transcription` → append `{role: "user", text}` to buffer
- On every `output_transcription` → append `{role: "agent", text}` to buffer
- On every tool_call / tool_response → append the I/O
- At compaction time → ship buffer + Prompt #2 to text model

Already feasible — we just don't need it until we have a way to actually
inject the resulting summary back into a new session as seed history. Gemini
Live's `system_instruction` is the only injection point at session start,
which works but is ugly (summary lives in system slot, not in history).

---

## UI Hooks (planned, deferred)

WebSocket events we'd emit so a future UI can render:

- `{type: "compaction_alert"}` — pre-alert fired
- `{type: "compaction_start"}` — compaction kicked off
- `{type: "compaction_complete", original_tokens, summary_tokens}` — done
- `{type: "token_usage", current, threshold}` — progress bar feed
- `{type: "pause_input"}` / `{type: "resume_input"}` — mic gating during compaction

Some of these (`token_usage`) we may emit now as part of the threshold
reminder; the rest wait for real compaction.

---

## Logging (planned, deferred)

Separate session log in `logs/YYYY-MM-DD_HH-MM-SS_session.log`:

- Per-line events: user_input, agent_output, tool_call, tool_result,
  token_count, compaction_start, compaction_complete, error
- Async fire-and-forget writes, never blocks the audio path
- One file per user session, includes pre- and post-compaction content so
  debugging stays possible

Deferred for now to keep v1 lean. Build when compaction lands.

---

## What We Shipped Instead (v1)

A single configurable threshold reminder:

- `.env` has `TOKEN_THRESHOLD` (default 65000).
- Server reads `usage_metadata.total_token_count` on every `turn_complete`.
- When the running total crosses `TOKEN_THRESHOLD`, the server injects the
  contents of `config/threshold_reminder.md` into the Live session **once**
  (as a system-side text message, invisible to the user).
- That prompt instructs the agent to gently, at a natural pause, suggest
  the user wrap up and start a fresh session — without alarming them.

Honest, minimal, works within the API we have.
