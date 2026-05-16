"""
Smriti graph_operation tool.

A single tool that the agent invokes with an `action` flag. All operations
work on a vault folder of flat markdown files. Every non-identity file is a
node identified by a 14-digit ID, used as its filename: {id}.md. Each node
has a YAML `aliases:` list in its frontmatter containing its title, so
Obsidian resolves [[id|Display]] correctly AND shows the human-readable
title in the graph view.
"""

import re
import secrets
from datetime import datetime, timezone
from pathlib import Path


IDENTITY_FILENAME = "identity.md"
ID_LENGTH = 14
LINK_PATTERN = re.compile(r"\[\[(\d{" + str(ID_LENGTH) + r"})(?:\|([^\]]+))?\]\]")
ANY_LINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")
FRONTMATTER_PATTERN = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


class GraphOperation:
    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path).resolve()
        self.vault_path.mkdir(parents=True, exist_ok=True)
        self._ensure_identity()

    # ---------- helpers ----------

    def _ensure_identity(self):
        identity = self.vault_path / IDENTITY_FILENAME
        if not identity.exists():
            now = self._today()
            identity.write_text(
                f"---\ntitle: Identity\ntype: identity\ncreated: {now}\nupdated: {now}\n---\n\n"
                "# Identity\n\n"
                "_Your working memory. This file is the always-on flash of who you are and what's active right now._\n\n"
                "## Core Identity\n\n"
                "## Life Phase\n\n"
                "## Active Focus\n",
                encoding="utf-8",
            )

    def _new_id(self) -> str:
        """Generate unique 14-digit ID, collision-checked against existing files."""
        while True:
            nid = "".join(secrets.choice("0123456789") for _ in range(ID_LENGTH))
            if not (self.vault_path / f"{nid}.md").exists():
                return nid

    def _node_path(self, node_id: str) -> Path:
        if not re.fullmatch(r"\d{" + str(ID_LENGTH) + r"}", node_id):
            raise ValueError(f"Invalid node id: {node_id!r}")
        return self.vault_path / f"{node_id}.md"

    def _parse_frontmatter(self, content: str) -> dict:
        m = FRONTMATTER_PATTERN.match(content)
        if not m:
            return {}
        meta = {}
        current_list_key = None
        for line in m.group(1).splitlines():
            # Handle YAML list items (- item)
            if line.strip().startswith("-") and current_list_key:
                item = line.strip()[1:].strip()
                meta[current_list_key].append(item)
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip()
                v = v.strip()
                # Detect inline list "[a, b]"
                if v.startswith("[") and v.endswith("]"):
                    items = [x.strip() for x in v[1:-1].split(",") if x.strip()]
                    meta[k] = items
                    current_list_key = None
                elif v == "":
                    # Start of multi-line list
                    meta[k] = []
                    current_list_key = k
                else:
                    meta[k] = v
                    current_list_key = None
        return meta

    def _build_frontmatter(self, meta: dict) -> str:
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

    def _strip_frontmatter(self, content: str) -> str:
        return FRONTMATTER_PATTERN.sub("", content, count=1)

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _validate_links(self, content: str) -> list:
        """Reject any [[...]] whose target isn't a 14-digit ID of an existing node."""
        errors = []
        existing_ids = set()
        for f in self.vault_path.glob("*.md"):
            if f.name == IDENTITY_FILENAME:
                continue
            if re.fullmatch(r"\d{" + str(ID_LENGTH) + r"}", f.stem):
                existing_ids.add(f.stem)

        for m in ANY_LINK_PATTERN.finditer(content):
            target = m.group(1).split("|", 1)[0].strip()
            if not re.fullmatch(r"\d{" + str(ID_LENGTH) + r"}", target):
                errors.append(
                    f"Link [[{m.group(1)}]] has invalid target '{target}'. "
                    f"Target MUST be a 14-digit numeric ID returned by create_node."
                )
            elif target not in existing_ids:
                errors.append(
                    f"Link [[{m.group(1)}]] points to ID {target} which does not exist. "
                    f"Call create_node first to get a real ID, then use it in the link."
                )
        return errors

    # ---------- actions ----------

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
        link_errors = self._validate_links(content)
        if link_errors:
            return {
                "status": "error",
                "error": "Invalid links in content. Fix these and retry.",
                "link_errors": link_errors,
            }
        path = self.vault_path / IDENTITY_FILENAME
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        meta = self._parse_frontmatter(existing)
        if not FRONTMATTER_PATTERN.match(content):
            meta = meta or {"title": "Identity", "type": "identity", "created": self._today()}
            meta["updated"] = self._today()
            body = self._build_frontmatter(meta) + "\n\n" + content.lstrip()
        else:
            m = FRONTMATTER_PATTERN.match(content)
            new_meta = self._parse_frontmatter(content)
            new_meta["updated"] = self._today()
            body = self._build_frontmatter(new_meta) + "\n" + content[m.end():]
        path.write_text(body, encoding="utf-8")
        return {"status": "success", "path": str(path), "bytes": len(body)}

    def read_node(self, node_id: str) -> dict:
        path = self._node_path(node_id)
        if not path.exists():
            return {"status": "error", "error": f"Node {node_id} not found"}
        content = path.read_text(encoding="utf-8")
        meta = self._parse_frontmatter(content)
        return {
            "status": "success",
            "id": node_id,
            "path": str(path),
            "title": meta.get("title", "Untitled"),
            "metadata": meta,
            "content": content,
            "links": self.extract_links(content)["links"],
        }

    def create_node(self, title: str, type: str, content: str = "") -> dict:
        if content:
            link_errors = self._validate_links(content)
            if link_errors:
                return {
                    "status": "error",
                    "error": "Invalid links in content. Fix these and retry.",
                    "link_errors": link_errors,
                }
        node_id = self._new_id()
        now = self._today()
        meta = {
            "id": node_id,
            "title": title,
            "aliases": [title],
            "type": type,
            "created": now,
            "updated": now,
        }
        body = self._build_frontmatter(meta) + f"\n\n# {title}\n\n{content}\n"
        path = self._node_path(node_id)
        path.write_text(body, encoding="utf-8")
        return {
            "status": "success",
            "id": node_id,
            "path": str(path),
            "title": title,
            "type": type,
        }

    def update_node(self, node_id: str, content: str) -> dict:
        path = self._node_path(node_id)
        if not path.exists():
            return {"status": "error", "error": f"Node {node_id} not found"}
        link_errors = self._validate_links(content)
        if link_errors:
            return {
                "status": "error",
                "error": "Invalid links in content. Fix these and retry.",
                "link_errors": link_errors,
            }
        existing = path.read_text(encoding="utf-8")
        meta = self._parse_frontmatter(existing)
        meta["updated"] = self._today()
        meta.setdefault("id", node_id)

        if FRONTMATTER_PATTERN.match(content):
            user_meta = self._parse_frontmatter(content)
            user_meta["id"] = node_id
            user_meta["updated"] = self._today()
            # Keep aliases in sync with title if title changed
            new_title = user_meta.get("title")
            if new_title:
                user_meta["aliases"] = [new_title]
            body = self._build_frontmatter(user_meta) + "\n" + self._strip_frontmatter(content)
        else:
            body = self._build_frontmatter(meta) + "\n\n" + content.lstrip()

        path.write_text(body, encoding="utf-8")
        return {"status": "success", "id": node_id, "path": str(path), "bytes": len(body)}

    def edit_node(self, node_id: str, old_string: str, new_string: str, replace_all: bool = False) -> dict:
        path = self._node_path(node_id)
        if not path.exists():
            return {"status": "error", "error": f"Node {node_id} not found"}
        content = path.read_text(encoding="utf-8")
        if old_string == new_string:
            return {"status": "error", "error": "old_string and new_string are identical"}
        if old_string not in content:
            return {"status": "error", "error": "old_string not found in node"}

        if replace_all:
            updated = content.replace(old_string, new_string)
        else:
            updated = content.replace(old_string, new_string, 1)

        link_errors = self._validate_links(updated)
        if link_errors:
            return {
                "status": "error",
                "error": "Edit would introduce invalid links. Fix new_string and retry.",
                "link_errors": link_errors,
            }

        meta = self._parse_frontmatter(updated)
        if meta:
            meta["updated"] = self._today()
            updated = self._build_frontmatter(meta) + "\n" + self._strip_frontmatter(updated)

        path.write_text(updated, encoding="utf-8")
        return {"status": "success", "id": node_id, "replace_all": replace_all}

    def list_nodes(self) -> dict:
        nodes = []
        for f in sorted(self.vault_path.glob("*.md")):
            if f.name == IDENTITY_FILENAME:
                continue
            if not re.fullmatch(r"\d{" + str(ID_LENGTH) + r"}", f.stem):
                continue
            try:
                content = f.read_text(encoding="utf-8")
                meta = self._parse_frontmatter(content)
                nodes.append({
                    "id": f.stem,
                    "title": meta.get("title", f.stem),
                    "type": meta.get("type", ""),
                    "updated": meta.get("updated", ""),
                })
            except Exception:
                continue
        return {"status": "success", "count": len(nodes), "nodes": nodes}

    def extract_links(self, content: str) -> dict:
        links = []
        for m in LINK_PATTERN.finditer(content):
            links.append({"id": m.group(1), "display": m.group(2) or m.group(1)})
        return {"status": "success", "links": links}

    def delete_node(self, node_id: str) -> dict:
        path = self._node_path(node_id)
        if not path.exists():
            return {"status": "error", "error": f"Node {node_id} not found"}
        backup = path.read_text(encoding="utf-8")
        path.unlink()
        return {"status": "success", "id": node_id, "backup": backup}


# ---------- dispatch ----------

def execute(graph: GraphOperation, action: str, **kwargs) -> dict:
    actions = {
        "read_identity": lambda: graph.read_identity(),
        "write_identity": lambda: graph.write_identity(kwargs["content"]),
        "read_node": lambda: graph.read_node(kwargs["node_id"]),
        "create_node": lambda: graph.create_node(kwargs["title"], kwargs["type"], kwargs.get("content", "")),
        "update_node": lambda: graph.update_node(kwargs["node_id"], kwargs["content"]),
        "edit_node": lambda: graph.edit_node(
            kwargs["node_id"], kwargs["old_string"], kwargs["new_string"], kwargs.get("replace_all", False)
        ),
        "list_nodes": lambda: graph.list_nodes(),
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
        "Operate on the user's second-brain vault. The vault contains identity.md plus flat node files named {14-digit-id}.md. "
        "Each node has a unique 14-digit ID in frontmatter plus an 'aliases' list containing its title, so Obsidian's graph view "
        "displays the human-readable title while links resolve by ID. "
        "Links between nodes use [[id|Display]] format where the ID traverses the graph. "
        "Choose the action and pass only the args that action needs."
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
            "node_id": {"type": "string", "description": "14-digit node ID. Required for read/update/edit/delete_node."},
            "title": {"type": "string", "description": "Title for create_node. Also stored as an alias so Obsidian graph displays it."},
            "type": {"type": "string", "description": "Node type (project|event|person|concept|goal|note|...). Required for create_node."},
            "content": {"type": "string", "description": "Markdown body. Used by write_identity, create_node, update_node, extract_links."},
            "old_string": {"type": "string", "description": "Exact text to find. Required for edit_node."},
            "new_string": {"type": "string", "description": "Replacement text. Required for edit_node."},
            "replace_all": {"type": "boolean", "description": "If true, edit_node replaces every occurrence; otherwise only the first."},
        },
        "required": ["action"],
    },
}
