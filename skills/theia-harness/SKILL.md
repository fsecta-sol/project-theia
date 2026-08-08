---
name: theia-harness
description: Apply the agent harness to every LLM invocation — verify grounding, enforce policy gate (ALLOW/DENY/ESCALATE), track token usage and cost, and manage context window state. Use before and after every skill that calls the LLM.
---

# Theia — Agent Harness (context management per shot)

The harness is a **deterministic supervisory wrapper** around every LLM shot. It guarantees
Theia runs sesuai — not drifting, not hallucinating — by verifying and gating every output.

## Four parts

```
1. GROUNDING VERIFIER (anti-hallucination)
   · every claim must cite a source (URL / on-chain tx / API response)
   · every P&L / screening number must come from a compute lib with logged inputs
   · unsourced claim → flagged; LLM money math → REJECTED

2. POLICY GATE (on-task + safe)
   · before any consequential action returns ALLOW / DENY / ESCALATE
   · edge cases go to human (Telegram), never guessed

3. CONTEXT WINDOW TRACKER (token budget)
   · stores every shot in the DB (llm_shots) with full inputs/outputs/policy
   · maintains rolling session summary so prompts stay cheap
   · per-model token + dollar budget; degrade when >80%

4. BUDGET BREAKER (survival)
   · per-source + per-model spend tracked
   · ≥80% degrade to cache / simpler model; 100% deny → shift to API-free work
```

## Procedure (wrap every LLM call)

### Before the LLM call

1. `theia-store.get_context_window(session_id)` → load current session state.
2. If `token_budget_remaining <= 0` or model budget spent:
   - **DEGRADE:** switch to smaller/cheaper model for this shot.
   - If fully spent → shift to API-free skill (`theia-learn-solana`, `theia-backtest`).
3. Build prompt with cheap context digest (not full history):
   ```python
   from compute.harness import context_digest, LlmShot
   shots = theia-store.get_session_shots(session_id, limit=20)
   cheap_context = context_digest([LlmShot(**s) for s in shots], max_tokens=600)
   ```
   Append `cheap_context` to system prompt so the LLM sees prior decisions without
   burning tokens on full chat history.

### After the LLM call

4. `execute_code`: run `verify_grounding(output_text, skill)`:
   ```python
   from compute.harness import verify_grounding
   g = verify_grounding(llm_output, skill="theia-paper-trade")
   ```
   Returns:
   - `has_source`: bool — found citation pattern
   - `has_computation_ref`: bool — referenced a compute lib
   - `money_math_source`: lib name or `"LLM"` if untraced
   - `missing_why`: list of flags

5. `execute_code`: run `policy_gate(skill, grounding, output_text, emergency_signals)`:
   ```python
   from compute.harness import policy_gate
   p = policy_gate("theia-paper-trade", g, llm_output,
                   emergency_signals=["rug", "lp pull", "mint live"])
   ```
   Returns `decision` = ALLOW | DENY | ESCALATE and `reason`.

6. **Enforce the decision:**
   - **ALLOW** → proceed with the skill's normal flow.
   - **DENY** → discard LLM output, log the rejection, retry with tighter prompt OR
     escalate to human if repeated.
   - **ESCALATE** → pause, send alert to Telegram with full shot details, wait for human.

7. Record the shot:
   ```python
   theia-store.record_llm_shot(
       shot_id=uuid4().hex[:12],
       session_id=session_id,
       skill="theia-paper-trade",
       inputs={"prompt": prompt_summary},
       outputs={"text": llm_output[:2000]},
       grounding_verdict=asdict(g),
       policy_decision=p.decision,
       policy_reason=p.reason,
       model="deepseek-v4-pro",
       prompt_tokens=prompt_tokens,
       completion_tokens=completion_tokens,
       total_tokens=total_tokens,
       cost_usd=estimate_cost(model, TokenUsage(...))
   )
   ```

8. Update context window:
   ```python
   theia-store.upsert_context_window(
       session_id,
       last_shot_id=shot_id,
       summary=new_summary,
       token_budget_remaining=old_budget - total_tokens,
       shots_count=shots_count + 1
   )
   ```

## DB Schema (theia-store)

| Table | Purpose |
|-------|---------|
| `llm_shots` | Immutable log of every LLM invocation with grounding + policy |
| `context_windows` | Rolling session state: summary, budget remaining, shot count |
| `knowledge_links` | Red-string graph between topics |

## Guardrails

- **The DB is the source of truth, never the model's memory.** Rebuild context FROM DB on boot.
- **Never run consequential action if policy = DENY.** Log and retry or escalate.
- **Token budget is a hard guard.** When hit, switch to deterministic compute-only work
  (backtest, screen scoring) that needs zero LLM tokens.
- **Grounding checks are deterministic regex + keyword, not another LLM call.**
  No infinite verification loop.
- **Session summaries are compressed heuristics, not LLM-generated.** Keep context cheap.
