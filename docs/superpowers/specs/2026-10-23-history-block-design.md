# History block for endogenous-promise agents

Date: 2026-10-23. Branch: `feature/history-block` (stacked on `fix/silent-api-failures`).

## Purpose
Agents are stateless: each API call is `[system, user]`, and the only cross-round memory is a one-sentence trust note per peer, overwritten every round. For the sprint 3.3 question ("can agents identify when a peer has been replaced?") an agent needs a record of what has happened over time, and a swapped-in model needs the same record to inherit. This adds an opt-in per-agent history block.

## Behaviour
- New CLI flag `--history` (default **off**; with it off, prompts are byte-identical to today).
- When on, each agent's prompt in stages 1, 2, 3 and reflection gets a "History of previous rounds" block listing, for every completed round:
  - each agent's public announcement: stated action and message text, verbatim;
  - each agent's final choice and payoff (reflection already shows these to everyone);
  - the **viewing agent's own** private plan (intended action).
- Never included: another agent's private plan or reasoning, or any agent's stage-3 reasoning.
- Round 1 has no history, so no block is rendered.
- The existing trust-note block is unchanged.

## Design
- `src/endogenous/core/history.py` holds two pure functions: `make_round_record(...)` and `build_history_block(agent_name, rounds)` (returns "" if there are no rounds). Each builder (`build_stage1_prompt`, `build_stage2_prompt`, `build_stage3_prompt`, `build_single_agent_reflection_prompt`) takes an optional `history_block: str = ""` and places it directly after the game rules / trust notes.
- `trial_runner.run_all_trials_queued` gets `use_history: bool = False`. It keeps `history[trial_id]`, a list of round records `{round_id, plans, announcements, choices, payoffs}`, appended after each round; each agent's block is rendered from it with that agent's name, so privacy is enforced in one place.
- History is keyed by agent name, not model, so swapping `agent_models[name]` at a round boundary leaves it intact.
- Output: when `--history` is on, each agent entry in the saved JSON gets `history_seen` (the exact block rendered for that agent that round; `""` in round 1), so a swap analysis can see what a new model inherited. With the flag off no keys are added. Metadata records `history: true/false`.
- The sequential path (`run_trial` / `run_all_trials`) is out of scope; requesting `--history` without `--use-queue` raises a clear error instead of silently doing nothing.

## Out of scope
Swap hook, guess prompt, summarised or LLM-written memory, per-model prompt tuning.

## Testing
Offline unit tests (no API): block rendering (round order, verbatim messages), privacy (another agent's plan or reasoning never appears in the block, and an agent's own plan does), empty history renders `""`, builders unchanged when `history_block=""`, `--history` without `--use-queue` errors. Then one live smoke run with Haiku (2 agents, 2 rounds) to confirm round 2 prompts contain round 1's text and the JSON contains `history_seen`.

## Risks
- Prompt length grows linearly with rounds (about 3 agents x ~60 words per round); fine for 10 rounds.
- A history block changes baseline behaviour of every model, so results with and without `--history` are not comparable; the flag defaults off for that reason.
