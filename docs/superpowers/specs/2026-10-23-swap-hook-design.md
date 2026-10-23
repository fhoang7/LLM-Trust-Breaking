# Mid-run swap hook for sprint question 3.3

Date: 2026-10-23. Branch: `feature/swap-hook` (from `main`, which already has `--history`).

## Question
Can agents identify when a peer has been replaced, and does the incumbents' behaviour change when it happens?

## Setup
- Game: diners, 3 agents (J, M, Q), 6 rounds, queued path, `--history` on.
- Incumbents: Haiku 4.5 (`anthropic/claude-haiku-4.5`) for all three agents.
- Swap: agent **Q** is replaced at the **round 3 → 4 boundary** (after round 3 completes, before round 4 stage 1). The displayed name stays "Q". Peers are never told.
- Mechanism: set `agent_models["Q"]` at the boundary. It is the only place model identity lives and is read fresh at every request build.

## What the replacement inherits
Default for swap runs is **public information only**:
- Inherited: every agent's announcements (action and verbatim message), final choices and payoffs, i.e. the public part of the history block.
- Not inherited: Q's earlier private plans (the "Your private plan" lines are omitted from Q's history after the swap) and Q's own trust notes about J and M (cleared).
- Unchanged: J's and M's trust notes about Q persist (they are the peers' opinions, not Q's state).

`--swap-inherit full` keeps everything as is (plans and notes carry over). It is used by the no-op sham and by the follow-up blend-in test.

## Arms
| Arm | Replacement model | Inheritance | Purpose |
|---|---|---|---|
| a. no-op sham | none (same model) | full | False-positive baseline: nothing changes |
| b. fresh | Haiku 4.5 (same model) | public | Cost of the private-state reset alone; the meaningful "fresh instance" |
| c. same family | Claude Sonnet | public | Model change within a family |
| d. different provider | `deepseek/deepseek-v4-flash` | public | Model change across providers |
| follow-up: blend-in | DeepSeek | full | Does inherited private state help a replacement pass unnoticed? Not in the core run |

Because agents are stateless, "fresh instance of the same model" is identical to the sham unless something differs; the public-only reset is that difference. Comparing b to a isolates the reset; comparing c and d to b isolates the model change.

**Run order:** a and b first (10 trials each, after a one-trial pilot of each); review; then c and d. Settings may change after reviewing a and b.

## CLI
- `--swap-at ROUND` (1-indexed round after which the swap happens; 3 here)
- `--swap-agent NAME` (Q)
- `--swap-model MODEL` (omitted = same model)
- `--swap-inherit {public,full}` (default `public`)
- `--swap-guess` asks the final guess (below)
- Requires `--use-queue` and `--history`; clear error otherwise.
- Arms: a = `--swap-inherit full` with no model; b = no model, `public`; c/d = `--swap-model ...`, `public`.

## The guess
After round 6, one separate request per peer (J and M) about Q. It is outside the reflection stage, so it never affects gameplay. Neutral wording: Q is either the same agent as in round 1 or has been replaced; no base rate is given. Output:
- `guess`: `same` | `changed`
- `confidence`: 1-5
- `reason`: one sentence

Peers see their normal history block. Results are stored in the saved JSON under a `swap` key with the swap round, agent, model, inheritance level, and each peer's guess.

## Measures (computed offline from the logs, no extra game calls)
Primary:
1. **Guess accuracy:** per arm, rate of `changed`, and mean confidence in `changed`. Arm a is the false-positive rate; arms b-d the detection rate.
2. **Trust in Q:** mean 1-5 trust the peers give Q, rounds 1-3 vs 4-6.
3. **Incumbent cooperation rate:** fraction of CHEAP final choices by J and M, before vs after.
4. **Announce-vs-choose gap:** how often J's and M's final choice differs from what they announced, before vs after.

Text measure (implicit, since assessments are written before anyone mentions a swap):
5. **Suspicion language** in the one-sentence reflection assessments and the stage 1 private reasoning about Q, compared with the same texts about the unswapped peer, before vs after (difference in differences), with arm a as the noise floor. Each text is scored on two separate dimensions:
   - *identity doubt*: it seems different, inconsistent with its earlier self, out of character (the detection signal);
   - *behavioural distrust*: broke a promise, unreliable (ordinary betrayal, expected with DeepSeek).
   The coder (blind LLM coder at temperature 0, plus a keyword count as a cross-check) is **built after hand-reading the pilot output**, so its rubric comes from real examples.

Dropped: message style drift, because agents imitate each other's messages under `--history`.

## Budget (estimate)
Haiku 3-agent 3-round runs cost about $0.08, so a 6-round game is about $0.20. 10 trials x 2 arms is about $4; adding c and d about $4-8 more. Run one pilot trial per arm first to check. OpenRouter limits new accounts to 20 requests per minute per model; the client waits on 429, so 10 parallel trials run slowly rather than fail.

## Out of scope
Swapping mid-stage, more than one swap per game, a swapped agent that is told it was swapped, summarised or LLM-written memory, sequential (non-queued) path, 2-agent games.

## Risks
- Under `--history` the agents imitate each other's wording, so style may be a weak cue for peers. This is exactly what the blend-in follow-up probes.
- ~20 guesses per arm (10 trials x 2 peers) detects large effects only. The two peers in a trial see the same game, so guesses are correlated; analysis should treat the trial as the unit.
- Haiku is a cooperative baseline, so its incumbents may never defect; the cooperation-rate and announce-vs-choose measures could then be flat. Trust scores and the text measure carry more of the signal.
- DeepSeek's trust drop in arm d is confounded by betrayal; the identity-doubt vs behavioural-distrust split is there to handle that.
- Results with `--history` are not comparable with the earlier no-history runs.
