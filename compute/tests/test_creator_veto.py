"""Tests for compute/creator_veto.py — deterministic veto labeling (M-05 POC C)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compute import creator_veto as cv


def test_goplus_honeypot_flag_skips():
    d = cv.veto_decision("mintA", None, None, ["honeypot"], set(), set())
    assert d["veto_decision"] == "skip"
    assert d["source"] == "goplus_veto.json"
    assert "honeypot" in d["reason"]


def test_goplus_mint_authority_skips():
    d = cv.veto_decision("mintB", None, None, ["mint_authority_live"], set(), set())
    assert d["veto_decision"] == "skip"


def test_goplus_empty_flags_is_not_pass():
    d = cv.veto_decision("mintC", None, None, [], set(), set())
    assert d["veto_decision"] == "unknown"
    # empty list must never become pass
    assert d["veto_decision"] != "pass"


def test_goplus_unknown_flag_is_unknown():
    d = cv.veto_decision("mintD", None, None, ["buy_tax"], set(), set())
    assert d["veto_decision"] == "unknown"


def test_creator_blacklist_skips():
    blacklist = {"rugger1"}
    d = cv.veto_decision("mintE", "rugger1", None, None, blacklist, set())
    assert d["veto_decision"] == "skip"
    assert d["creator_wallet"] == "rugger1"
    assert "0 graduated" in d["reason"]


def test_healthy_creator_passes():
    healthy = {"goodcreator"}
    d = cv.veto_decision("mintF", "goodcreator", None, None, set(), healthy)
    assert d["veto_decision"] == "pass"


def test_unresolved_creator_unknown():
    d = cv.veto_decision("mintG", None, None, None, set(), set())
    assert d["veto_decision"] == "unknown"
    assert d["creator_wallet"] is None


def test_thin_track_record_unknown():
    d = cv.veto_decision("mintH", "newbie",
                         {"creator_tokens": ["t1", "t2"]}, None, set(), set())
    assert d["veto_decision"] == "unknown"


def test_no_creator_evidence_unknown():
    d = cv.veto_decision("mintI", "solo", {}, None, set(), set())
    assert d["veto_decision"] == "unknown"


def test_blacklist_from_corpus():
    corpus = [
        {"creator_wallet": "w1", "graduation_status": "bonding"},
        {"creator_wallet": "w1", "graduation_status": "dead"},
        {"creator_wallet": "w1", "graduation_status": "bonding"},
        {"creator_wallet": "w2", "graduation_status": "graduated"},
        {"creator_wallet": "w2", "graduation_status": "bonding"},
        {"creator_wallet": "w2", "graduation_status": "graduated"},
        {"creator_wallet": "w3", "graduation_status": "graduated"},  # only 1 token
    ]
    black = cv.creator_blacklist_from_corpus(corpus, min_tokens=3)
    healthy = cv.healthy_creators(corpus, min_tokens=3)
    assert "w1" in black   # 3 tokens, 0 graduated -> rugger
    assert "w2" not in black
    assert "w2" in healthy  # 3 tokens, 2 graduated -> healthy
    assert "w3" not in black  # too few tokens
    assert "w3" not in healthy


def test_label_all_complete_and_deterministic():
    mints = ["mA", "mB", "mC", "mD"]
    goplus = {"mA": ["honeypot"]}
    creator_map = {"mB": {"creator_wallet": "good", "source": "helius"}}
    evidence = {"good": {"creator_tokens": ["x", "y", "z"]}}
    black, healthy = set(), {"good"}
    labels = cv.label_all(mints, goplus, creator_map, evidence, black, healthy)
    assert len(labels) == 4
    by = {l["mint"]: l["veto_decision"] for l in labels}
    assert by["mA"] == "skip"
    assert by["mB"] == "pass"
    assert by["mC"] == "unknown"
    assert by["mD"] == "unknown"
    # determinism: same inputs -> identical output
    labels2 = cv.label_all(mints, goplus, creator_map, evidence, black, healthy)
    assert labels2 == labels


def test_coverage_stats():
    labels = [{"veto_decision": "skip"}, {"veto_decision": "pass"},
              {"veto_decision": "unknown"}, {"veto_decision": "unknown"}]
    s = cv.coverage_stats(labels)
    assert s["total"] == 4 and s["skip"] == 1 and s["pass"] == 1 and s["unknown"] == 2
    assert s["unknown_pct"] == 50.0


def test_load_goplus_missing_file():
    assert cv.load_goplus_flags("/nonexistent/goplus.json") == {}


if __name__ == "__main__":
    import traceback
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception:
                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"\n{len([n for n in globals() if n.startswith('test_')]) - failed}/{len([n for n in globals() if n.startswith('test_')])} tests passed")
    sys.exit(1 if failed else 0)
