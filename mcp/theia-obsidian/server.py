#!/usr/bin/env python3
"""theia-obsidian — vault gateway MCP for Theia's second brain.

Theia dumps; human curates.  Append-only by design.  No dedup, no locking,
no section parsing.  Write guard is hardcoded: Theia may only touch inbox,
hypotheses, archives, and meta.

Vault root: $THEIA_VAULT or ~/.hermes/profiles/theia/vault
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("theia-obsidian")

VAULT_ROOT = Path(os.environ.get("THEIA_VAULT", str(Path.home() / ".hermes" / "profiles" / "theia" / "vault")))

_ALLOWED_PREFIXES = (
    "00-Inbox/",
    "02-Projects/theia-hypotheses/",
    "04-Archives/theia/",
    "99-Meta/",
)

_DENIED_PREFIXES = (
    "03-Areas/",
    "01-Action/",
    ".obsidian/",
    "templates/",
)


def _resolve(path: str) -> Path:
    p = (VAULT_ROOT / path).resolve()
    if not str(p).startswith(str(VAULT_ROOT.resolve())):
        raise ValueError("path escapes vault")
    return p


def _guard(path: str, action: str = "write") -> None:
    """Hardcoded write guard. Raises ValueError on deny."""
    if action != "write":
        return
    norm = path.replace("\\", "/").lstrip("/")
    if not norm.endswith(".md"):
        raise ValueError("only .md files may be written")
    for denied in _DENIED_PREFIXES:
        if norm.startswith(denied):
            raise ValueError(f"write denied: {norm} matches denied prefix {denied}")
    for allowed in _ALLOWED_PREFIXES:
        if norm.startswith(allowed):
            return
    raise ValueError(f"write denied: {norm} not in allowed prefixes")


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        try:
            end = lines.index("---", 1)
        except ValueError:
            end = 0
        if end > 0:
            try:
                fm = json.loads("\n".join(lines[1:end]))  # loose YAML-ish: we accept JSON in frontmatter
            except json.JSONDecodeError:
                fm = {}
            return fm, "\n".join(lines[end + 1 :])
    return {}, text


# ── Tools ───────────────────────────────────────────────────────────────────


@mcp.tool()
def read_note(path: str) -> dict:
    """Read a vault note. Returns frontmatter, body, mtime, and wiki-links."""
    p = _resolve(path)
    if not p.exists():
        return {"ok": False, "error": "not found", "path": path}
    text = p.read_text(encoding="utf-8")
    fm, body = _parse_frontmatter(text)
    wikilinks = [m[2:-2] for m in _WIKILINK_RE.findall(body)]
    return {
        "ok": True,
        "path": path,
        "frontmatter": fm,
        "body": body,
        "wikilinks": wikilinks,
        "mtime": int(p.stat().st_mtime),
    }


@mcp.tool()
def write_note(path: str, content: str, frontmatter: dict | None = None) -> dict:
    """Create a new note (overwriting is allowed only within guard)."""
    _guard(path)
    p = _resolve(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = frontmatter or {}
    header = f"---\n{json.dumps(fm, indent=2)}\n---\n\n" if fm else ""
    p.write_text(header + content, encoding="utf-8")
    return {"ok": True, "path": path, "bytes_written": len(header) + len(content)}


@mcp.tool()
def append_to_note(path: str, content: str, section: str = "") -> dict:
    """Append content to an existing note.  Creates file if it does not exist."""
    _guard(path)
    p = _resolve(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        if section:
            f.write(f"\n\n## {section}\n")
        f.write(content)
        f.write("\n")
    return {"ok": True, "path": path}


@mcp.tool()
def batch_read_notes(paths: list[str]) -> dict:
    """Read up to 20 notes in one call."""
    notes = []
    for path in paths[:20]:
        p = _resolve(path)
        if p.exists():
            text = p.read_text(encoding="utf-8")
            fm, body = _parse_frontmatter(text)
            notes.append({"path": path, "frontmatter": fm, "body": body})
        else:
            notes.append({"path": path, "error": "not found"})
    return {"ok": True, "notes": notes}


@mcp.tool()
def search_notes(query: str, folder: str = "", max_results: int = 10) -> dict:
    """Search vault notes using ripgrep. Falls back to Python scan if rg missing."""
    target = VAULT_ROOT / folder if folder else VAULT_ROOT
    cmd = [
        "rg", "--json", "--max-count", str(max_results * 3),
        "-C", "2", "-i", query, str(target),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except (FileNotFoundError, PermissionError):
        return _fallback_search(query, target, max_results)
    matches = []
    for line in proc.stdout.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "match" and "data" in obj:
            d = obj["data"]
            path = d["path"].get("text", "")
            lines = d.get("lines", {})
            text = lines.get("text", "")
            line_no = lines.get("line_number", 0)
            matches.append({"path": path, "line_no": line_no, "snippet": text[:300]})
            if len(matches) >= max_results:
                break
    return {"ok": True, "matches": matches}


def _fallback_search(query: str, target: Path, max_results: int) -> dict:
    import re
    pat = re.compile(re.escape(query), re.IGNORECASE)
    matches = []
    for p in target.rglob("*.md"):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if pat.search(line):
                matches.append({"path": str(p.relative_to(VAULT_ROOT)), "line_no": i, "snippet": line[:300]})
                if len(matches) >= max_results:
                    return {"ok": True, "matches": matches, "backend": "python"}
    return {"ok": True, "matches": matches, "backend": "python"}


@mcp.tool()
def note_exists(path: str) -> dict:
    """Check if a note exists and return mtime."""
    p = _resolve(path)
    return {"ok": True, "exists": p.exists(), "mtime": int(p.stat().st_mtime) if p.exists() else 0}


@mcp.tool()
def get_vault_stats() -> dict:
    """Scan the vault and return counts."""
    counts = {"total": 0, "inbox": 0, "hypotheses": 0, "archives": 0, "meta": 0, "other": 0}
    for p in VAULT_ROOT.rglob("*.md"):
        rel = str(p.relative_to(VAULT_ROOT)).replace("\\", "/")
        counts["total"] += 1
        if rel.startswith("00-Inbox/"):
            counts["inbox"] += 1
        elif rel.startswith("02-Projects/theia-hypotheses/"):
            counts["hypotheses"] += 1
        elif rel.startswith("04-Archives/theia/"):
            counts["archives"] += 1
        elif rel.startswith("99-Meta/"):
            counts["meta"] += 1
        else:
            counts["other"] += 1
    return {"ok": True, **counts, "vault_root": str(VAULT_ROOT)}


import re as _re_module
_WIKILINK_RE = _re_module.compile(r"\[\[([^\]]+)\]\]")

if __name__ == "__main__":
    mcp.run()
