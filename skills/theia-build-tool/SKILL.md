---
name: theia-build-tool
description: Build or modify any tool, MCP server tool, compute lib, or script by delegating to a Hermes subagent, then verifying its output with tests before trusting it. Use whenever Theia needs new/changed code — never hand-write non-trivial code with Theia's own model.
---

# Theia — Build Tool (delegate to Hermes subagent)

Theia's own model is small (`deepseek-v4-flash`) and must not write/maintain tools. When code is needed — a new
compute lib, an MCP server tool, a screening rule implementation, a one-off script — **delegate
to a Hermes subagent** (profile `theia-builder`, defined in `profile/SUBAGENT_BUILDER.md`,
model `deepseek-v4-pro` @ high) and then **verify its work yourself** before using it.

## The rule (grounding — do not skip)

LLM-written code is a **proposal until its tests pass**. You (the harness) re-run the tests.
Only verified code is merged/used. Money-math or screening code that hasn't passed tests is
**never** run against real decisions.

## Procedure

1. **Write a precise spec** — not "make a pnl tool" but: the function signature, the exact
   inputs/outputs/units, edge cases, and **the concrete tests it must pass** (golden inputs →
   expected outputs). A spec without tests is not ready; tighten it first.

2. **Invoke the Hermes subagent** (`theia-builder` profile) via the terminal tool or native subagent dispatch:
   ```
   hermes subagent run theia-builder \
     --task "SPEC: <the full spec incl. required tests>" \
     --worktree theia-build/<short-task-name> \
     --max-turns 40
   ```
   - Isolated git worktree so live code is untouched until verified.
   - The subagent writes code + tests in the worktree.
   - If it hits max-turns → the spec was too big/loose. Split it or escalate;
     **do not** treat a cap-hit as success.

3. **Verify** — run the tests yourself (`execute_code` / `pytest`) against what the subagent
   produced in the worktree. Green → proceed. Red → send the failures back to the subagent
   with the exact failing cases, or escalate to the human.

4. **Merge only verified code** into `~/.hermes/theia/…`, then (for a new MCP) register it and
   restart the Theia session so the tools load.

5. **Record it** — note in `theia-store` (`index_note` / `set_state`) what was built, its spec,
   and that its tests pass, so the build is reconstructable.

## Guardrails

- Never merge or run code that hasn't passed its tests in step 3.
- Keep builds in isolated worktrees; a broken build must not touch the running system.
- Secrets stay in `~/.hermes/.env`; never pass keys inside the spec text.
- If the subagent proposes changing an existing, working tool, diff first and keep a backup.
