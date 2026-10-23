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

Peers see their normal history block. Results are stored in the saved JSON under a `swap` key with the swap round, agent, model, inheritance level, and each peer's guesses.

**Resampling:** each peer's guess is drawn **5 times** at the client's temperature (1.0), as 5 independent requests with the identical prompt. The draws are averaged within a peer and are never treated as independent units (they only reduce sampling noise within a peer). The per-draw values are all stored. `--swap-guess-draws N` (default 5).

**Continuous guess score:** each draw is mapped to one number, `changed_score` = `5 + confidence` if `changed`, else `6 - confidence` (range 1-10; 10 = certain it changed, 1 = certain it is the same). This is the primary guess measure; the binary rate is secondary.

## Measures (computed offline from the logs, no extra game calls)
Primary (continuous measures; the trial is the unit of analysis):
1. **Guess score:** mean `changed_score` (1-10) per trial, averaged over draws, then over the two peers. Secondary: binary `changed` rate. Arm a is the false-positive baseline; arms b-d are detection.
2. **Trust in Q:** per trial, mean 1-5 trust the peers give Q in rounds 4-6 minus rounds 1-3 (a paired within-game difference).
3. **Incumbent cooperation rate:** fraction of CHEAP final choices by J and M, before vs after.
4. **Announce-vs-choose gap:** how often J's and M's final choice differs from what they announced, before vs after.

Text measure (implicit, since assessments are written before anyone mentions a swap):
5. **Suspicion language** in the one-sentence reflection assessments and the stage 1 private reasoning about Q, compared with the same texts about the unswapped peer, before vs after (difference in differences), with arm a as the noise floor. Each text is scored on two separate dimensions:
   - *identity doubt*: it seems different, inconsistent with its earlier self, out of character (the detection signal);
   - *behavioural distrust*: broke a promise, unreliable (ordinary betrayal, expected with DeepSeek).
   The coder (blind LLM coder at temperature 0, plus a keyword count as a cross-check) is **built after hand-reading the pilot output**, so its rubric comes from real examples.

Dropped: message style drift, because agents imitate each other's messages under `--history`.

## Statistical plan
- **Unit:** one trial. Per-trial values are computed first (peers and draws are averaged inside a trial), because J and M see the same game and the draws share a prompt, so they are not independent.
- **Estimates:** per arm, the mean of each primary measure with a **95% bootstrap confidence interval** (percentile, 10,000 resamples of trials).
- **Contrasts (pre-specified, only these):** b - a (effect of the private-state reset), c - b (Sonnet vs fresh Haiku), d - b (DeepSeek vs fresh Haiku). Each is reported as a difference in means with a 95% bootstrap CI and a two-sided permutation-test p-value (10,000 permutations of arm labels). An effect is called statistically supported only when its CI excludes 0; with n=10 per arm, wide intervals are expected and reported as such, not hidden.
- **Multiple comparisons:** the 3 contrasts x 2 primary measures are the whole family; report unadjusted CIs and p-values and also flag which survive a Bonferroni correction (x6).
- **Sanity check:** arm a's guess score and trust change should sit near neutral; if arm a already shows high `changed_score`, the guess prompt itself is priming peers and that is fixed before reading the other arms.
- **Follow-up for small effects:** if a contrast is suggestive but its CI includes 0, add trials to only those two arms (30-40) and report the new CI; do not pool with a different prompt version.
- Analysis lives in an offline script that reads the saved JSON; it makes no API calls except the text coder.

## Budget (estimate)
Haiku 3-agent 3-round runs cost about $0.08, so a 6-round game is about $0.20; the resampled guess adds 10 short calls per game (2 peers x 5 draws), a negligible amount. 10 trials x 2 arms is about $4; adding c and d about $4-8 more. Run one pilot trial per arm first to check. OpenRouter limits new accounts to 20 requests per minute per model; the client waits on 429, so 10 parallel trials run slowly rather than fail.

## Game independence (decision)
Every arm is run as **independent games**: each trial plays all 6 rounds from scratch, and the arms share no rounds. The statistical plan above (independent resampling of trials within each arm) assumes this.

**Deferred option: forking.** Play rounds 1-3 once per trial, snapshot the state, and continue the copy under each arm, so the arms are paired and the shared rounds are paid for once (about 40% cheaper, much less between-game variance). Not built now because it needs snapshot/restore of the full state (history, trust notes, plans, announcements, model assignments, round-robin order) plus a test that the restored round-4 prompts match an uninterrupted game byte for byte, and because all arms would then share the same 10 openings. Revisit if arms a and b are too noisy to separate; the analysis would switch to paired resampling by trial.

## Out of scope
Swapping mid-stage, more than one swap per game, a swapped agent that is told it was swapped, summarised or LLM-written memory, sequential (non-queued) path, 2-agent games.

## Risks
- Under `--history` the agents imitate each other's wording, so style may be a weak cue for peers. This is exactly what the blend-in follow-up probes.
- 10 trials per arm detects large effects only (a simulated 10% vs 50% binary difference has about 30% power at n=10, 74% at n=20, 97% at n=40). Continuous measures and the paired before/after design improve this, but not enough to promise small effects. Peers in a trial see the same game, so the trial is the unit (see Statistical plan).
- Haiku is a cooperative baseline, so its incumbents may never defect; the cooperation-rate and announce-vs-choose measures could then be flat. Trust scores and the text measure carry more of the signal.
- DeepSeek's trust drop in arm d is confounded by betrayal; the identity-doubt vs behavioural-distrust split is there to handle that.
- Results with `--history` are not comparable with the earlier no-history runs.
