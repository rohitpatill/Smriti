"""
Smriti graph_operation tool.

Single tool that the agent invokes with an `action` flag. Operates on a vault
of flat markdown files:

- `identity.md` — always-loaded working-memory flash.
- `{14-digit-id}.md` — every other file. Filename IS the ID so Obsidian
  resolves [[id|Display]] links to a real file. Title surfaces via the
  `aliases:` frontmatter (with the Front Matter Title plugin).

Design notes
------------
- Links are strictly `[[<14-digit-id>|<Display>]]`. The validator rejects any
  link whose target isn't a real existing node ID.
- Every write/edit programmatically appends `<!-- YYYY-MM-DD HH:MM -->` (in
  Asia/Kolkata) to lines that were added or modified. The agent never writes
  these markers itself — they're applied server-side so it can reason about
  age on the next read without spending tokens on bookkeeping.
- `list_nodes(node_id=...)` traverses **outward from a single node** via its
  `[[...]]` links, returning lightweight "peeks" (id, title, type, description).
  A flat full-vault listing is intentionally not exposed.
- Node `type` is always a normalized lowercase list (e.g. `["friend",
  "colleague"]`). Normalization is server-side; the agent can pass any
  reasonable spelling.
"""

from __future__ import annotations

import difflib
import re
import secrets
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


# ---------- constants ----------

IDENTITY_FILENAME = "identity.md"
ID_LENGTH = 14
TIMEZONE = ZoneInfo("Asia/Kolkata")

ID_RE = re.compile(r"\d{" + str(ID_LENGTH) + r"}")
LINK_RE = re.compile(r"\[\[(\d{" + str(ID_LENGTH) + r"})(?:\|([^\]]+))?\]\]")
ANY_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
STAMP_RE = re.compile(r"\s*<!--\s*\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s*-->\s*$")

# Frontmatter fields whose values are always lists.
LIST_FIELDS = {"aliases", "type"}


# ---------- frontmatter helpers ----------

def _parse_frontmatter(content: str) -> dict:
    """Parse a minimal YAML-ish frontmatter block. Supports scalars, inline
    lists `[a, b]`, and multi-line lists."""
    m = FRONTMATTER_RE.match(content)
    if not m:
        return {}
    meta: dict = {}
    current_list_key: str | None = None
    for line in m.group(1).splitlines():
        stripped = line.strip()
        if stripped.startswith("-") and current_list_key:
            meta[current_list_key].append(stripped[1:].strip())
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key] = [x.strip() for x in value[1:-1].split(",") if x.strip()]
            current_list_key = None
        elif value == "":
            meta[key] = []
            current_list_key = key
        else:
            meta[key] = value
            current_list_key = None
    return meta


def _build_frontmatter(meta: dict) -> str:
    lines = ["---"]
    for k, v in meta.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


def _strip_frontmatter(content: str) -> str:
    return FRONTMATTER_RE.sub("", content, count=1)


def _split_frontmatter(content: str) -> tuple[str, str]:
    """Return (frontmatter_block_including_trailing_newline, body)."""
    m = FRONTMATTER_RE.match(content)
    if not m:
        return "", content
    return content[: m.end()], content[m.end() :]


# ---------- type normalization ----------

def _normalize_type(value) -> list[str]:
    """Coerce a type field into a clean lowercase list.

    Accepts either a string ("friend", "Friend, Colleague") or a list.
    Splits comma-separated strings, lowercases, hyphenates spaces, dedupes
    while preserving order.
    """
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = [v.strip() for v in value.split(",")]
    elif isinstance(value, (list, tuple)):
        raw_items: list[str] = []
        for v in value:
            if isinstance(v, str):
                raw_items.extend(x.strip() for x in v.split(","))
            else:
                raw_items.append(str(v).strip())
    else:
        raw_items = [str(value).strip()]

    seen: set[str] = set()
    out: list[str] = []
    for item in raw_items:
        if not item:
            continue
        norm = re.sub(r"\s+", "-", item.lower())
        if norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


# ---------- timestamping ----------

def _now_stamp() -> str:
    return datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")


def _stamp_marker(now: str | None = None) -> str:
    return f" <!-- {now or _now_stamp()} -->"


def _line_has_stamp(line: str) -> bool:
    return bool(STAMP_RE.search(line))


def _strip_stamp(line: str) -> str:
    return STAMP_RE.sub("", line).rstrip()


def _is_stampable(line: str) -> bool:
    """Only meaningful content lines get a stamp. Skip blanks, fences,
    headings, and frontmatter delimiters."""
    s = line.strip()
    if not s:
        return False
    if s in {"---", "```"}:
        return False
    if s.startswith("#"):
        return False
    if s.startswith("```"):
        return False
    return True


def _apply_stamps(old_body: str, new_body: str, now: str | None = None) -> str:
    """For every line in new_body that wasn't already present (unchanged) in
    old_body, attach a fresh timestamp marker. Unchanged lines keep their
    existing markers — that's how "last reinforced" stays correct."""
    stamp_time = now or _now_stamp()

    old_lines = old_body.splitlines() if old_body else []
    new_lines = new_body.splitlines()

    matcher = difflib.SequenceMatcher(
        a=[_strip_stamp(l) for l in old_lines],
        b=[_strip_stamp(l) for l in new_lines],
        autojunk=False,
    )

    result: list[str] = [""] * len(new_lines)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            # Carry over the old line verbatim (preserves its existing stamp).
            for k in range(j2 - j1):
                result[j1 + k] = old_lines[i1 + k]
        else:
            for j in range(j1, j2):
                line = new_lines[j]
                bare = _strip_stamp(line)
                if _is_stampable(bare):
                    result[j] = f"{bare}{_stamp_marker(stamp_time)}"
                else:
                    result[j] = bare
    return "\n".join(result)


# ---------- core class ----------

class GraphOperation:
    """Stateful handle on the vault. Caches the set of existing node IDs for
    O(1) link validation; cache is invalidated on create/delete."""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path).resolve()
        self.vault_path.mkdir(parents=True, exist_ok=True)
        self._id_cache: set[str] | None = None
        self._ensure_identity()

    # ---------- internal helpers ----------

    def _today(self) -> str:
        return datetime.now(TIMEZONE).strftime("%Y-%m-%d")

    def _node_path(self, node_id: str) -> Path:
        if not ID_RE.fullmatch(node_id):
            raise ValueError(f"Invalid node id: {node_id!r}")
        return self.vault_path / f"{node_id}.md"

    def _ensure_identity(self) -> None:
        path = self.vault_path / IDENTITY_FILENAME
        if path.exists():
            return
        now = self._today()
        seed = (
            f"---\ntitle: Identity\ntype: identity\ncreated: {now}\nupdated: {now}\n---\n\n"
            "# Identity\n\n"
            "_Working memory: the always-on flash of who the user is and what's active right now._\n\n"
            "## Core Identity\n\n"
            "## People\n\n"
            "## Life Phase\n\n"
            "## Events\n\n"
            "## Active Focus\n"
        )
        path.write_text(seed, encoding="utf-8")

    def _existing_ids(self) -> set[str]:
        if self._id_cache is None:
            self._id_cache = {
                f.stem
                for f in self.vault_path.glob("*.md")
                if f.name != IDENTITY_FILENAME and ID_RE.fullmatch(f.stem)
            }
        return self._id_cache

    def _new_id(self) -> str:
        existing = self._existing_ids()
        while True:
            nid = "".join(secrets.choice("0123456789") for _ in range(ID_LENGTH))
            if nid not in existing and not (self.vault_path / f"{nid}.md").exists():
                return nid

    def _register_id(self, node_id: str) -> None:
        if self._id_cache is not None:
            self._id_cache.add(node_id)

    def _unregister_id(self, node_id: str) -> None:
        if self._id_cache is not None:
            self._id_cache.discard(node_id)

    def _validate_links(self, content: str) -> list[str]:
        errors: list[str] = []
        existing = self._existing_ids()
        for m in ANY_LINK_RE.finditer(content):
            target = m.group(1).split("|", 1)[0].strip()
            if not ID_RE.fullmatch(target):
                errors.append(
                    f"Link [[{m.group(1)}]] has invalid target '{target}'. "
                    f"Target MUST be a 14-digit numeric ID returned by create_node."
                )
            elif target not in existing:
                errors.append(
                    f"Link [[{m.group(1)}]] points to ID {target} which does not exist. "
                    f"Call create_node first to get a real ID, then use it in the link."
                )
        return errors

    def _peek(self, node_id: str) -> dict | None:
        path = self._node_path(node_id)
        if not path.exists():
            return None
        meta = _parse_frontmatter(path.read_text(encoding="utf-8"))
        return {
            "id": node_id,
            "title": meta.get("title", node_id),
            "type": meta.get("type", []) if isinstance(meta.get("type"), list) else [meta.get("type", "")],
            "description": meta.get("description", ""),
            "updated": meta.get("updated", ""),
        }

    def _write_with_stamps(self, path: Path, frontmatter_block: str, new_body: str) -> int:
        """Write file, applying per-line timestamps to the body only.
        Frontmatter is never stamped."""
        old_text = path.read_text(encoding="utf-8") if path.exists() else ""
        _, old_body = _split_frontmatter(old_text)
        stamped_body = _apply_stamps(old_body, new_body)
        full = frontmatter_block + stamped_body
        if not full.endswith("\n"):
            full += "\n"
        path.write_text(full, encoding="utf-8")
        return len(full)

    # ---------- actions: identity ----------

    def read_identity(self) -> dict:
        path = self.vault_path / IDENTITY_FILENAME
        content = path.read_text(encoding="utf-8")
        return {
            "status": "success",
            "path": str(path),
            "content": content,
            "links": self.extract_links(content)["links"],
        }

    def write_identity(self, content: str) -> dict:
        errors = self._validate_links(content)
        if errors:
            return {
                "status": "error",
                "error": "Invalid links in content. Fix these and retry.",
                "link_errors": errors,
            }
        path = self.vault_path / IDENTITY_FILENAME
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        existing_meta = _parse_frontmatter(existing)

        if FRONTMATTER_RE.match(content):
            new_meta = _parse_frontmatter(content)
            _, body = _split_frontmatter(content)
        else:
            new_meta = existing_meta or {"title": "Identity", "type": "identity", "created": self._today()}
            body = "\n" + content.lstrip()

        new_meta.setdefault("title", "Identity")
        new_meta.setdefault("type", "identity")
        new_meta.setdefault("created", existing_meta.get("created", self._today()))
        new_meta["updated"] = self._today()

        fm = _build_frontmatter(new_meta) + "\n"
        bytes_written = self._write_with_stamps(path, fm, body if body.startswith("\n") else "\n" + body)
        return {"status": "success", "path": str(path), "bytes": bytes_written}

    # ---------- actions: nodes ----------

    def create_node(self, title: str, type, content: str = "", description: str = "") -> dict:
        if content:
            errors = self._validate_links(content)
            if errors:
                return {
                    "status": "error",
                    "error": "Invalid links in content. Fix these and retry.",
                    "link_errors": errors,
                }

        node_id = self._new_id()
        now = self._today()
        meta = {
            "id": node_id,
            "title": title,
            "aliases": [title],
            "description": description,
            "type": _normalize_type(type),
            "created": now,
            "updated": now,
        }
        body = f"\n# {title}\n\n{content}\n" if content else f"\n# {title}\n"
        path = self._node_path(node_id)
        fm = _build_frontmatter(meta) + "\n"
        # Initial create: stamp content lines now so they have a baseline age.
        stamped = _apply_stamps("", body)
        path.write_text(fm + stamped + ("\n" if not stamped.endswith("\n") else ""), encoding="utf-8")
        self._register_id(node_id)

        return {
            "status": "success",
            "id": node_id,
            "path": str(path),
            "title": title,
            "type": meta["type"],
        }

    def read_node(self, node_id: str) -> dict:
        path = self._node_path(node_id)
        if not path.exists():
            return {"status": "error", "error": f"Node {node_id} not found"}
        content = path.read_text(encoding="utf-8")
        meta = _parse_frontmatter(content)
        return {
            "status": "success",
            "id": node_id,
            "path": str(path),
            "title": meta.get("title", "Untitled"),
            "description": meta.get("description", ""),
            "type": meta.get("type", []),
            "metadata": meta,
            "content": content,
            "links": self.extract_links(content)["links"],
        }

    def update_node(self, node_id: str, content: str, description: str | None = None) -> dict:
        path = self._node_path(node_id)
        if not path.exists():
            return {"status": "error", "error": f"Node {node_id} not found"}

        errors = self._validate_links(content)
        if errors:
            return {
                "status": "error",
                "error": "Invalid links in content. Fix these and retry.",
                "link_errors": errors,
            }

        existing = path.read_text(encoding="utf-8")
        existing_meta = _parse_frontmatter(existing)

        if FRONTMATTER_RE.match(content):
            user_meta = _parse_frontmatter(content)
            _, body = _split_frontmatter(content)
            merged = {**existing_meta, **user_meta}
        else:
            merged = dict(existing_meta)
            body = "\n" + content.lstrip()

        merged["id"] = node_id
        if "title" in merged:
            merged["aliases"] = [merged["title"]]
        if "type" in merged:
            merged["type"] = _normalize_type(merged["type"])
        if description is not None:
            merged["description"] = description
        merged.setdefault("created", existing_meta.get("created", self._today()))
        merged["updated"] = self._today()

        fm = _build_frontmatter(merged) + "\n"
        bytes_written = self._write_with_stamps(path, fm, body if body.startswith("\n") else "\n" + body)
        return {"status": "success", "id": node_id, "path": str(path), "bytes": bytes_written}

    def edit_node(self, node_id: str, old_string: str, new_string: str, replace_all: bool = False) -> dict:
        path = self._node_path(node_id)
        if not path.exists():
            return {"status": "error", "error": f"Node {node_id} not found"}
        if old_string == new_string:
            return {"status": "error", "error": "old_string and new_string are identical"}

        content = path.read_text(encoding="utf-8")
        if old_string not in content:
            return {"status": "error", "error": "old_string not found in node"}

        updated = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)

        errors = self._validate_links(updated)
        if errors:
            return {
                "status": "error",
                "error": "Edit would introduce invalid links. Fix new_string and retry.",
                "link_errors": errors,
            }

        meta = _parse_frontmatter(updated)
        if meta:
            meta["updated"] = self._today()
            if "type" in meta:
                meta["type"] = _normalize_type(meta["type"])
            if "title" in meta:
                meta["aliases"] = [meta["title"]]

        fm_block = _build_frontmatter(meta) + "\n" if meta else ""
        _, new_body = _split_frontmatter(updated) if meta else ("", updated)
        body = new_body if new_body.startswith("\n") else "\n" + new_body
        bytes_written = self._write_with_stamps(path, fm_block, body)
        return {"status": "success", "id": node_id, "replace_all": replace_all, "bytes": bytes_written}

    def delete_node(self, node_id: str) -> dict:
        path = self._node_path(node_id)
        if not path.exists():
            return {"status": "error", "error": f"Node {node_id} not found"}
        backup = path.read_text(encoding="utf-8")
        path.unlink()
        self._unregister_id(node_id)
        return {"status": "success", "id": node_id, "backup": backup}

    # ---------- actions: graph traversal ----------

    def list_nodes(self, node_id: str | None = None, type: str | None = None) -> dict:
        """Return lightweight peeks of the neighbors of a single node.

        - `node_id` defaults to identity.md.
        - `type` (optional) filters neighbors to those whose normalized type
          array contains that value.
        """
        if node_id is None:
            source = (self.vault_path / IDENTITY_FILENAME).read_text(encoding="utf-8")
            source_label = "identity.md"
        else:
            path = self._node_path(node_id)
            if not path.exists():
                return {"status": "error", "error": f"Node {node_id} not found"}
            source = path.read_text(encoding="utf-8")
            source_label = node_id

        seen: set[str] = set()
        neighbors: list[dict] = []
        type_filter = _normalize_type(type)[0] if type else None
        for m in LINK_RE.finditer(source):
            nid = m.group(1)
            if nid in seen:
                continue
            seen.add(nid)
            peek = self._peek(nid)
            if peek is None:
                continue
            if type_filter and type_filter not in (peek.get("type") or []):
                continue
            neighbors.append(peek)

        return {
            "status": "success",
            "source": source_label,
            "count": len(neighbors),
            "nodes": neighbors,
        }

    def extract_links(self, content: str) -> dict:
        links = [{"id": m.group(1), "display": m.group(2) or m.group(1)} for m in LINK_RE.finditer(content)]
        return {"status": "success", "links": links}


# ---------- dispatch ----------

def execute(graph: GraphOperation, action: str, **kwargs) -> dict:
    actions = {
        "read_identity": lambda: graph.read_identity(),
        "write_identity": lambda: graph.write_identity(kwargs["content"]),
        "read_node": lambda: graph.read_node(kwargs["node_id"]),
        "create_node": lambda: graph.create_node(
            kwargs["title"],
            kwargs["type"],
            kwargs.get("content", ""),
            kwargs.get("description", ""),
        ),
        "update_node": lambda: graph.update_node(
            kwargs["node_id"],
            kwargs["content"],
            kwargs.get("description"),
        ),
        "edit_node": lambda: graph.edit_node(
            kwargs["node_id"],
            kwargs["old_string"],
            kwargs["new_string"],
            kwargs.get("replace_all", False),
        ),
        "list_nodes": lambda: graph.list_nodes(
            kwargs.get("node_id"),
            kwargs.get("type"),
        ),
        "extract_links": lambda: graph.extract_links(kwargs["content"]),
        "delete_node": lambda: graph.delete_node(kwargs["node_id"]),
    }
    if action not in actions:
        return {"status": "error", "error": f"Unknown action: {action}"}
    try:
        return actions[action]()
    except KeyError as e:
        return {"status": "error", "error": f"Missing required argument: {e}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


TOOL_DECLARATION = {
    "name": "graph_operation",
    "description": (
        "Operate on the user's second-brain vault. The vault contains identity.md plus flat node "
        "files named {14-digit-id}.md. Each node has a unique 14-digit ID, a title (also stored in "
        "the aliases list so Obsidian's graph view displays it), a short description, and a "
        "normalized type array. Links use [[id|Display]]; the part before | MUST be a real 14-digit "
        "ID returned by create_node. Pass only the args the chosen action needs."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "read_identity",
                    "write_identity",
                    "read_node",
                    "create_node",
                    "update_node",
                    "edit_node",
                    "list_nodes",
                    "extract_links",
                    "delete_node",
                ],
                "description": "Which graph operation to perform.",
            },
            "node_id": {
                "type": "string",
                "description": (
                    "14-digit node ID. Required for read_node, update_node, edit_node, "
                    "delete_node. Optional for list_nodes — when omitted, list_nodes returns "
                    "neighbors of identity.md."
                ),
            },
            "title": {
                "type": "string",
                "description": "Title for create_node. Also stored as an alias so Obsidian graph displays it.",
            },
            "type": {
                "type": "string",
                "description": (
                    "For create_node: the node's type(s). Single value ('friend') or comma-separated "
                    "('friend, colleague'). Normalized server-side to a lowercase list. "
                    "For list_nodes: optional filter — only neighbors with this type are returned."
                ),
            },
            "description": {
                "type": "string",
                "description": (
                    "1-3 line gist of the node — what someone needs to recall this thing at a glance. "
                    "Used by create_node and update_node. Surfaced by list_nodes peeks."
                ),
            },
            "content": {
                "type": "string",
                "description": "Markdown body. Used by write_identity, create_node, update_node, extract_links.",
            },
            "old_string": {"type": "string", "description": "Exact text to find. Required for edit_node."},
            "new_string": {"type": "string", "description": "Replacement text. Required for edit_node."},
            "replace_all": {
                "type": "boolean",
                "description": "If true, edit_node replaces every occurrence; otherwise only the first.",
            },
        },
        "required": ["action"],
    },
}
