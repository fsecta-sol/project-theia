"""Knowledge graph auto-discovery — follow 'red strings' from web content.

Given a seed topic (e.g., "AMM"), scrape Solana docs / articles and extract
related concepts (e.g., "DLMM", "CLMM", "Orca", "Raydium"). Build a directed
link graph so Learn Phase can auto-crawl from one topic to the next.

Pure stdlib + theia_net.request_json. No LLM calls here — deterministic extraction.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from collections import Counter

# ── Solana concept lexicon (seed terms to scan for) ──────────────────────────

_SOLANA_CONCEPTS = {
    "amm", "cpmm", "clmm", "dlmm", "dex", "jupiter", "raydium", "orca",
    "meteora", "pump.fun", "bonding curve", "liquidity pool", "lp",
    "token", "spl token", "mint", "freeze authority", "mint authority",
    "honeypot", "rug pull", "wash trading", "mev", "sniper",
    "account model", "pda", "program derived address", "cpi",
    "cross-program invocation", "fee", "priority fee", "compute unit",
    "slot", "finality", "validator", "staking", "epoch",
    "wrapped sol", "wsol", "usdc", "stablecoin", "bridge",
    "graduation", "migration", "bonding", "market maker", "order book",
    "limit order", "vamm", "concentrated liquidity", "tick", "range",
    "impermanent loss", "yield", "farming", "reward", "emission",
    "nft", "candy machine", "metadata", "token standard",
    "governance", "dao", "proposal", "vote", "treasury",
    "wallet", "phantom", "solflare", "ledger", "seed phrase",
    "private key", "public key", "address", "transaction", "signature",
    "block", "blockhash", "rent", "lamport", "sol",
    "bpf", "rust", "anchor", "sealevel", "runtime",
}

# Normalization: strip punctuation, lower, collapse whitespace
_NORM_RE = re.compile(r"[^a-z0-9\s]")


def _norm(text: str) -> str:
    return _NORM_RE.sub("", text.lower()).strip()


def _extract_paragraphs(html: str) -> list[str]:
    """Naive paragraph extraction from HTML. Pure regex, no deps."""
    # Strip tags roughly
    plain = re.sub(r"<[^>]+>", " ", html)
    # Collapse whitespace
    plain = re.sub(r"\s+", " ", plain)
    # Split on sentence boundaries
    sentences = re.split(r"(?<=[.!?])\s+", plain)
    # Group into ~300-char paragraphs
    paragraphs, buf = [], ""
    for s in sentences:
        if len(buf) + len(s) < 300:
            buf += " " + s
        else:
            if buf:
                paragraphs.append(buf.strip())
            buf = s
    if buf:
        paragraphs.append(buf.strip())
    return paragraphs


def _score_concept_presence(paragraphs: list[str], concept: str) -> float:
    """How strongly a concept appears in text (density + exact matches)."""
    term = _norm(concept)
    total = sum(len(p) for p in paragraphs)
    if total == 0:
        return 0.0
    hits = sum(1 for p in paragraphs if term in _norm(p))
    return min(1.0, hits / max(1, len(paragraphs) * 0.3))


# ── Public API ─────────────────────────────────────────────────────────────


def discover_related(seed_topic: str, content_html: str,
                     known_notes: list[str] | None = None) -> list[dict]:
    """Scan HTML content for Solana concepts related to seed_topic.

    Returns list of {to_topic, confidence, source_snippet} sorted desc.
    Confidence is heuristic based on co-occurrence density.
    """
    paragraphs = _extract_paragraphs(content_html)
    seed_norm = _norm(seed_topic)

    # Only consider paragraphs that mention the seed topic
    seed_paras = [p for p in paragraphs if seed_norm in _norm(p)]
    if not seed_paras:
        return []

    scores: Counter[str] = Counter()
    snippets: dict[str, str] = {}

    for concept in _SOLANA_CONCEPTS:
        if concept == seed_norm or concept in seed_norm:
            continue
        conf = _score_concept_presence(seed_paras, concept)
        if conf > 0.15:   # threshold — must appear in >15% of seed paragraphs
            scores[concept] = conf
            # grab first paragraph containing it as snippet
            for p in seed_paras:
                if _norm(concept) in _norm(p):
                    snippets[concept] = p[:200]
                    break

    # Boost if concept is already in known_notes (vault) — stronger signal
    known_set = set(_norm(k) for k in (known_notes or []))
    out = []
    for topic, conf in scores.most_common(10):
        if topic in known_set:
            conf = min(1.0, conf * 1.2)
        out.append({
            "to_topic": topic,
            "confidence": round(conf, 3),
            "source_snippet": snippets.get(topic, ""),
        })

    return sorted(out, key=lambda x: x["confidence"], reverse=True)


def fetch_and_discover(seed_topic: str, url: str,
                       known_notes: list[str] | None = None,
                       ttl_cache: int = 3600) -> dict:
    """Fetch a URL and run discovery on its content.

    Uses theia_net.request_json (actually fetches HTML via HTTP).
    Cached via theia_net.DiskCache if instantiated externally.
    """
    try:
        # request_json returns parsed JSON; for HTML we need raw text
        # Fallback: urllib directly for HTML pages
        import urllib.request
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) theia/0.1"}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode(errors="replace")
    except Exception as e:
        return {"ok": False, "error": str(e), "seed": seed_topic, "url": url}

    links = discover_related(seed_topic, html, known_notes)
    return {
        "ok": True,
        "seed": seed_topic,
        "url": url,
        "links_found": len(links),
        "links": links,
    }


def build_graph_path(start: str, target: str,
                     link_db: list[dict],
                     max_hops: int = 4) -> list[dict] | None:
    """BFS over a knowledge link DB to find shortest path start→target.

    link_db items: {from_note, to_note, confidence}.
    Returns path as list of hops or None.
    """
    from collections import deque

    # Build adjacency
    adj: dict[str, list[tuple[str, float]]] = {}
    for row in link_db:
        a, b = row.get("from_note", ""), row.get("to_note", "")
        conf = row.get("confidence", 0.5)
        if a and b:
            adj.setdefault(a, []).append((b, conf))
            adj.setdefault(b, []).append((a, conf))

    visited = {start}
    queue = deque([(start, [])])
    while queue:
        node, path = queue.popleft()
        if node == target:
            return path
        if len(path) >= max_hops:
            continue
        for neighbor, conf in adj.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                hop = {
                    "from": node,
                    "to": neighbor,
                    "confidence": conf,
                    "hop": len(path) + 1,
                }
                queue.append((neighbor, path + [hop]))
    return None
