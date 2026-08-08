"""Golden-input tests for Theia compute libs."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from compute import amm_sim, exit_engine, expectancy, gas_sim, pnl, screen_score  # noqa: E402
from compute.wilson import wilson_lower_bound  # noqa: E402


def test_wilson():
    assert wilson_lower_bound(3, 3) < wilson_lower_bound(30, 50)
    assert wilson_lower_bound(0, 0) == 0.0


def test_expectancy_gate():
    # high win-rate but terrible payoff → must FAIL the gate (the DpDf3mLv lesson)
    r = expectancy.evaluate([1, 1, 1, -33])   # 75% win, PF = 3/33
    assert r["win_rate"] == 0.75 and r["profit_factor"] < 1 and r["passes"] is False
    # low win-rate, fat tail → PASSES
    r2 = expectancy.evaluate([-1, -1, -1, 10])
    assert r2["win_rate"] == 0.25 and r2["expectancy"] > 0 and r2["passes"] is True


def test_fifo_pnl():
    swaps = [
        {"ts": 1, "side": "buy", "base_mint": "A", "base_qty": 10, "quote_qty": 10},
        {"ts": 2, "side": "sell", "base_mint": "A", "base_qty": 10, "quote_qty": 20},   # +10
        {"ts": 3, "side": "buy", "base_mint": "B", "base_qty": 10, "quote_qty": 10},
        {"ts": 4, "side": "sell", "base_mint": "B", "base_qty": 10, "quote_qty": 4},     # -6
    ]
    pnls = pnl.fifo_trade_pnls(swaps)
    assert len(pnls) == 2 and math.isclose(sum(pnls), 4.0, rel_tol=1e-9)
    m = expectancy.evaluate(pnls)
    assert math.isclose(m["profit_factor"], 10 / 6, rel_tol=1e-9)


def test_amm_and_gas():
    f = amm_sim.buy_fill(1.0, 1000.0, 10.0, fee=0.0)
    assert math.isclose(f["tokens_out"], 1000 / 11, rel_tol=1e-9) and f["slippage"] > 0
    fee = gas_sim.swap_fee_sol(cu_price_microlamports=50000, cu_limit=200000)
    assert math.isclose(fee, (5000 + 10000) / 1e9, rel_tol=1e-9)
    assert gas_sim.swap_fee_sol(first_buy=True) > fee


def _row(ts, o, h, l, c):
    return [ts, o, h, l, c, 0.0]


def test_exit_ladder_and_stop():
    r = exit_engine.simulate_exit(1.0, 0, [_row(60, 1, 1, 0.5, 0.5)])
    assert r["final_reason"] == "hard_stop" and math.isclose(r["realized_price"], 0.65)
    path = [_row(60, 1, 2.5, 1, 2.5), _row(120, 2.5, 5, 2.5, 5), _row(180, 5, 5, 3, 3)]
    r2 = exit_engine.simulate_exit(1.0, 0, path, {"time_stop_secs": 10**9})
    reasons = [e[2] for e in r2["exits"]]
    assert "tp_2x" in reasons and "tp_4x" in reasons and "trail" in reasons
    assert math.isclose(r2["realized_price"], 2.9375, rel_tol=1e-9)


def test_screen():
    # clean token passes
    good = screen_score.screen(
        {"is_honeypot": 0, "buy_tax": 0, "sell_tax": 0, "mint_auth_live": 0,
         "freeze_auth_live": 0, "lp_locked": True, "top10_share": 0.2},
        {"liquidity_usd": 100000, "unique_buyers": 90, "total_buys": 100,
         "volume_24h_usd": 200000, "top_wallet_vol_share": 0.1})
    assert good["verdict"] == "pass"
    # mint authority live → hard reject
    bad = screen_score.screen(
        {"mint_auth_live": 1, "lp_locked": True}, {"liquidity_usd": 100000})
    assert bad["verdict"] == "reject" and "mint-authority-live" in bad["reject_reason"]


def test_harness_grounding():
    from compute.harness import verify_grounding, policy_gate, estimate_cost, TokenUsage

    # output with compute ref → passes
    g = verify_grounding("expectancy computed by compute/expectancy.py = 0.03", "theia-backtest")
    assert g.has_computation_ref is True
    assert g.money_math_source == "expectancy"

    # output with money number but no compute ref → LLM flagged
    g2 = verify_grounding("profit factor is 1.5", "theia-evaluate-expectancy")
    assert g2.money_math_source == "LLM"

    # policy: consequential + LLM money math → DENY
    p = policy_gate("theia-evaluate-expectancy", g2, "profit factor is 1.5")
    assert p.decision == "DENY"

    # policy: non-consequential → ALLOW even without source
    p2 = policy_gate("theia-learn-solana", g2, "profit factor is 1.5")
    assert p2.decision == "ALLOW"

    # cost estimate
    cost = estimate_cost("deepseek-v4-pro", TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500))
    assert cost > 0


def test_harness_context_digest():
    from compute.harness import LlmShot, PolicyResult, context_digest
    shots = [
        LlmShot(session_id="S1", skill="theia-screen-token", policy=PolicyResult(decision="ALLOW")),
        LlmShot(session_id="S1", skill="theia-paper-trade", policy=PolicyResult(decision="DENY")),
    ]
    d = context_digest(shots)
    assert "theia-screen-token" in d and "theia-paper-trade" in d


def test_knowledge_graph_discovery():
    from compute.knowledge_graph import discover_related, build_graph_path

    html = """
    <p>Concentrated liquidity AMMs like DLMM from Meteora allow LPs to place
    liquidity within specific price ranges, improving capital efficiency over
    traditional CPMM models used by Raydium.</p>
    <p>Orca also uses concentrated liquidity with Whirlpools, similar to
    Uniswap v3 but on Solana. DLMM extends this with bin-based pricing.</p>
    """
    links = discover_related("AMM", html)
    topics = {l["to_topic"] for l in links}
    assert "dlmm" in topics or "clmm" in topics or "orca" in topics or "raydium" in topics

    # BFS path
    db = [
        {"from_note": "amm", "to_note": "dlmm", "confidence": 0.8},
        {"from_note": "dlmm", "to_note": "meteora", "confidence": 0.7},
    ]
    path = build_graph_path("amm", "meteora", db)
    assert path is not None and len(path) == 2
    assert path[0]["to"] == "dlmm"
    assert path[1]["to"] == "meteora"
