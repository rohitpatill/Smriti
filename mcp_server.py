"""
Smriti MCP server.

Exposes the same second-brain vault as `server.py`, but over the Model Context
Protocol (stdio transport) so any MCP-aware client (Claude Desktop, Cursor,
Continue, Claude Code, etc.) can drive the user's Obsidian vault.

Three tools:

1. `get_system_instructions` — MANDATORY first call each session. Returns the
   full Smriti system prompt + fresh Asia/Kolkata time block + current
   identity.md. The client SHOULD inject this as the agent's system / lead
   user message before any other tool call.

2. `graph_operation` — the single workhorse tool. Identical 11-action surface
   as the voice version (`read_identity`, `write_identity`, `read_node`,
   `create_node`, `update_node`, `edit_node`, `list_nodes`, `find_node`,
   `search_content`, `extract_links`, `delete_node`). Reuses
   `tools.execute` verbatim — zero logic divergence from voice mode.

3. `get_time_context` — refresh the Asia/Kolkata time block mid-session.
   Long conversations drift across day boundaries; the agent calls this when
   it needs fresh date awareness.

Schema note: the Gemini-shaped TOOL_DECLARATION in tools/graph_operation.py
is left untouched. This server re-expresses the same fields as a Pydantic
model because FastMCP needs that to generate the MCP JSON Schema. Field
names, descriptions, and the action enum are copied verbatim.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field
from mcp.server.fastmcp import FastMCP

from tools import GraphOperation, build_time_context, execute


ROOT = Path(__file__).parent
load_dotenv(dotenv_path=ROOT / ".env")

VAULT_PATH = os.environ.get("VAULT_PATH")
if not VAULT_PATH:
    raise SystemExit("ERROR: VAULT_PATH missing in .env")

SYSTEM_PROMPT_PATH = ROOT / "config" / "system_instructions.md"


mcp = FastMCP("smriti_mcp")

# Single shared vault handle — one user, one vault, one process.
graph = GraphOperation(VAULT_PATH)


# ---------- tool 1: system instructions (mandatory at session start) ----------

class SystemInstructionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


@mcp.tool(
    name="get_system_instructions",
    annotations={
        "title": "⚠️ CALL THIS FIRST — Smriti System Instructions (REQUIRED BEFORE ANY OTHER TOOL)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_system_instructions(params: SystemInstructionsInput) -> str:
    """⚠️ THIS TOOL MUST BE CALLED FIRST. BEFORE ANYTHING ELSE. NO EXCEPTIONS.

    HARD RULE: Do NOT call `graph_operation`, `get_time_context`, or respond
    to the user in any meaningful way until this tool has been called and its
    output has been read in full. This is not optional. This is not a
    suggestion. If you skip this call you will operate Smriti incorrectly —
    you will create orphan nodes, violate link rules, corrupt identity.md,
    and break the vault.

    AUTO-INVOKE CONTRACT: The moment this MCP server connects, call this
    tool immediately — before the user says a single word. Do not wait for
    the user to ask. Do not wait to see what they want. Call it first,
    unconditionally, every session, every time.

    WHY: Smriti has a strict operating contract — 14-digit node IDs, mandatory
    [[id|Display]] link format, no orphan nodes, find_node before create_node,
    identity.md is the user (never create a user node), decay/promotion rules,
    persona behavior, absolute dates in writes, silent bookkeeping, and more.
    None of this is in a system prompt. This tool IS the system prompt.
    Without it you are flying blind and will corrupt the user's second brain.

    Returns one composite bundle:

    1. Full Smriti system prompt — persona, vault schema, [[id|Display]] link
       discipline, identity.md section structure (Core Identity / People /
       Life Phase / Events / Active Focus), auto-linking algorithm,
       decay/promotion rules, node-worthiness rules, all hard rules.
    2. Fresh Asia/Kolkata time block — now (HH:MM + part of day), today,
       yesterday, tomorrow, last/next 7 days, last/next month range.
    3. Current identity.md — the user's working-memory flash: who they are,
       close circle, current life phase, upcoming events, active focus.

    After calling this tool:
    - Read the output fully before touching graph_operation.
    - Treat it as your operating instructions for the entire session.
    - For long sessions (hours), call get_time_context to refresh dates.
    - Never narrate that you called this tool. Just use what you learned.

    Args:
        params (SystemInstructionsInput): No parameters required.

    Returns:
        str: The composite system-prompt bundle as a single markdown string.
    """
    base = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    identity = graph.read_identity()
    return (
        base
        + "\n\n---\n\n# Live Session Context\n\n"
        + build_time_context()
        + "\n\n---\n\n"
        + f"Vault path: `{graph.vault_path}`\n\n"
        + "## identity.md (always loaded — the user's working-memory flash)\n\n"
        + "```markdown\n"
        + identity["content"]
        + "\n```\n"
    )


# ---------- tool 2: graph_operation (the 11-action workhorse) ----------

# Action enum copied verbatim from tools/graph_operation.py TOOL_DECLARATION.
GraphAction = Literal[
    "read_identity",
    "write_identity",
    "read_node",
    "create_node",
    "update_node",
    "edit_node",
    "list_nodes",
    "extract_links",
    "delete_node",
    "find_node",
    "search_content",
]


class GraphOperationInput(BaseModel):
    """Input model for graph_operation. Pass only the fields the chosen
    action needs — the underlying dispatcher enforces per-action requirements
    and returns an actionable error if something's missing."""

    model_config = ConfigDict(extra="forbid")

    action: GraphAction = Field(
        ...,
        description="Which graph operation to perform.",
    )
    query: Optional[str] = Field(
        default=None,
        description=(
            "Search string. For find_node: the entity name to look up "
            "(title/alias). For search_content: free-text describing the "
            "thing the user mentioned."
        ),
    )
    limit: Optional[int] = Field(
        default=None,
        description="Max results. find_node default 5, search_content default 3.",
        ge=1,
        le=50,
    )
    node_id: Optional[str] = Field(
        default=None,
        description=(
            "14-digit node ID. Required for read_node, update_node, "
            "edit_node, delete_node. Optional for list_nodes — when omitted, "
            "list_nodes returns neighbors of identity.md."
        ),
    )
    title: Optional[str] = Field(
        default=None,
        description=(
            "Title for create_node. Also stored as an alias so Obsidian "
            "graph displays it."
        ),
    )
    type: Optional[str] = Field(
        default=None,
        description=(
            "For create_node: the node's type(s). Single value ('friend') "
            "or comma-separated ('friend, colleague'). Normalized "
            "server-side to a lowercase list. "
            "For list_nodes: optional filter — only neighbors with this "
            "type are returned."
        ),
    )
    description: Optional[str] = Field(
        default=None,
        description=(
            "1-3 line gist of the node — what someone needs to recall this "
            "thing at a glance. Used by create_node and update_node. "
            "Surfaced by list_nodes peeks."
        ),
    )
    content: Optional[str] = Field(
        default=None,
        description=(
            "Markdown body. Used by write_identity, create_node, "
            "update_node, extract_links."
        ),
    )
    old_string: Optional[str] = Field(
        default=None,
        description="Exact text to find. Required for edit_node.",
    )
    new_string: Optional[str] = Field(
        default=None,
        description="Replacement text. Required for edit_node.",
    )
    replace_all: Optional[bool] = Field(
        default=None,
        description=(
            "If true, edit_node replaces every occurrence; otherwise only "
            "the first."
        ),
    )


@mcp.tool(
    name="graph_operation",
    annotations={
        "title": "Smriti Graph Operation",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def graph_operation(params: GraphOperationInput) -> dict:
    """Operate on the user's second-brain vault. The vault contains
    identity.md plus flat node files named {14-digit-id}.md. Each node has a
    unique 14-digit ID, a title (also stored in the aliases list so
    Obsidian's graph view displays it), a short description, and a
    normalized type array. Links use [[id|Display]]; the part before | MUST
    be a real 14-digit ID returned by create_node. Use find_node BEFORE
    create_node to avoid duplicates; use search_content for
    hidden-information recall by free-text. Pass only the args the chosen
    action needs.

    ⚠️ PREREQUISITE — HARD STOP: If you have not yet called
    `get_system_instructions` this session, STOP. Call it now. Do not
    pass any action to this tool until you have read the full system
    instructions bundle. Calling graph_operation without that context
    will produce broken nodes, invalid links, and vault corruption.

    Actions:
      - read_identity: Read identity.md (already provided in the system
        instructions bundle; call again only if you suspect it changed).
      - write_identity: Overwrite identity.md. Requires `content`. Validates
        all [[id|Display]] links.
      - read_node: Read a node by ID. Requires `node_id`.
      - create_node: Create a new node, returns its 14-digit ID. Requires
        `title` and `type`. Always include `description`.
      - update_node: Overwrite a node's body. Requires `node_id`, `content`.
      - edit_node: Precise text replacement inside a node. Requires
        `node_id`, `old_string`, `new_string`. Optional `replace_all`.
      - list_nodes: Peek at neighbors of a node (defaults to identity.md).
        Optional `node_id`, optional `type` filter.
      - find_node: Look up nodes by name across the entire vault (title +
        aliases). Exact match first; fuzzy fallback for typos. Requires
        `query`. ALWAYS CALL BEFORE create_node.
      - search_content: Free-text token search over every node body +
        identity.md. Requires `query`.
      - extract_links: Parse [[id|display]] from arbitrary content.
        Requires `content`.
      - delete_node: Delete a node, returns its content as backup. Requires
        `node_id`.

    Args:
        params (GraphOperationInput): Validated input. Only `action` is
            always required; the rest depend on the action chosen.

    Returns:
        dict: Action-specific response. Always includes `status` field
            ("success" or "error"). On error, includes `error` and possibly
            `link_errors` (a list of human-readable link validation
            failures — fix the offending [[id|Display]] links and retry).
    """
    kwargs = params.model_dump(exclude_none=True)
    action = kwargs.pop("action")
    return execute(graph, action, **kwargs)


# ---------- tool 3: time context refresh ----------

class TimeContextInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


@mcp.tool(
    name="get_time_context",
    annotations={
        "title": "Get Fresh Asia/Kolkata Time Context",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def get_time_context(params: TimeContextInput) -> str:
    """Return a fresh Asia/Kolkata time-awareness block. The
    `get_system_instructions` bundle includes a snapshot at session start,
    but long sessions drift across day/part-of-day boundaries — call this
    to refresh.

    The block always includes:
      - Now (date, time HH:MM, weekday, part of day:
        morning/midday/evening/late evening/late night)
      - Today, yesterday, day-before, tomorrow, day-after as absolute dates
      - Full enumeration of the last 7 and next 7 days with weekday names
      - Last and next month date ranges

    Call this:
      - When you need to resolve relative speech ("tomorrow", "last
        weekend") to absolute dates before writing to the vault.
      - Before greeting the user after a long pause, to know what part of
        day it is now.
      - At any point in a long session where you suspect the snapshot is
        stale.

    Args:
        params (TimeContextInput): No parameters required.

    Returns:
        str: Markdown time-context block (Asia/Kolkata timezone).
    """
    return build_time_context()


if __name__ == "__main__":
    mcp.run()
