"""theia-obsidian golden tests — mock filesystem, no real vault required."""
import importlib.util
import sys
import tempfile
from pathlib import Path

# ── Mock mcp modules ───────────────────────────────────────────────────────

class _MockFastMCP:
    def __init__(self, name): self.name = name
    def tool(self):
        def decorator(fn): return fn
        return decorator

sys.modules["mcp"] = type(sys)("mcp")
sys.modules["mcp.server"] = type(sys)("mcp.server")
sys.modules["mcp.server.fastmcp"] = type(sys)("mcp.server.fastmcp")
sys.modules["mcp.server.fastmcp"].FastMCP = _MockFastMCP

# ── Load server module ─────────────────────────────────────────────────────

spec = importlib.util.spec_from_file_location("obsidian_server", Path(__file__).resolve().parents[1] / "server.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["obsidian_server"] = mod
spec.loader.exec_module(mod)


# ── Fixtures ───────────────────────────────────────────────────────────────

def _fresh_vault() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="vault-"))
    mod.VAULT_ROOT = tmp
    return tmp


# ── Tests ───────────────────────────────────────────────────────────────────

def test_write_guard_allows_inbox():
    vault = _fresh_vault()
    mod.write_note("00-Inbox/_knowledge/amm.md", "body", {"title": "AMM"})
    assert (vault / "00-Inbox/_knowledge/amm.md").exists()


def test_write_guard_denies_areas():
    vault = _fresh_vault()
    try:
        mod.write_note("03-Areas/concepts/amm.md", "body")
    except ValueError as e:
        assert "denied" in str(e).lower()
        return
    raise AssertionError("expected ValueError for denied prefix")


def test_write_guard_denies_non_md():
    vault = _fresh_vault()
    try:
        mod.write_note("00-Inbox/_knowledge/secret.txt", "body")
    except ValueError as e:
        assert "only .md" in str(e).lower()
        return
    raise AssertionError("expected ValueError for non-md")


def test_append_to_note_creates_and_appends():
    vault = _fresh_vault()
    mod.append_to_note("00-Inbox/_knowledge/pump.md", "initial", section="Sources")
    mod.append_to_note("00-Inbox/_knowledge/pump.md", "extra fact")
    text = (vault / "00-Inbox/_knowledge/pump.md").read_text()
    assert "initial" in text
    assert "extra fact" in text


def test_read_note_parses_frontmatter():
    vault = _fresh_vault()
    note = vault / "02-Projects/theia-hypotheses/H-0001.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text('---\n{"title": "H1", "status": "draft"}\n---\n\nrationale here', encoding="utf-8")
    res = mod.read_note("02-Projects/theia-hypotheses/H-0001.md")
    assert res["ok"] is True
    assert res["frontmatter"]["status"] == "draft"
    assert "rationale" in res["body"]


def test_batch_read_notes():
    vault = _fresh_vault()
    for i in range(3):
        p = vault / "00-Inbox" / f"n{i}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"note {i}", encoding="utf-8")
    res = mod.batch_read_notes(["00-Inbox/n0.md", "00-Inbox/n1.md", "00-Inbox/missing.md"])
    assert res["ok"] is True
    assert len(res["notes"]) == 3
    assert res["notes"][2].get("error") == "not found"


def test_search_notes_fallback():
    vault = _fresh_vault()
    (vault / "00-Inbox").mkdir(parents=True, exist_ok=True)
    (vault / "00-Inbox" / "a.md").write_text("solana mechanics", encoding="utf-8")
    (vault / "00-Inbox" / "b.md").write_text("nothing here", encoding="utf-8")
    res = mod.search_notes("mechanics", folder="00-Inbox", max_results=5)
    assert res["ok"] is True
    assert len(res["matches"]) == 1
    assert "a.md" in res["matches"][0]["path"]


def test_get_vault_stats():
    vault = _fresh_vault()
    (vault / "00-Inbox").mkdir(parents=True, exist_ok=True)
    (vault / "00-Inbox" / "x.md").write_text("x", encoding="utf-8")
    (vault / "02-Projects/theia-hypotheses").mkdir(parents=True, exist_ok=True)
    (vault / "02-Projects/theia-hypotheses" / "H-1.md").write_text("h", encoding="utf-8")
    res = mod.get_vault_stats()
    assert res["ok"] is True
    assert res["inbox"] == 1
    assert res["hypotheses"] == 1
    assert res["other"] == 0
