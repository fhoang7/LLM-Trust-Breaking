# Can agents tell when a peer has been replaced? Preliminary findings

> **Note (25 Oct):** the intervals in this working report were computed with BCa bootstrap intervals. The paper tables and figure (`outputs/paper/`) and the analysis code now use plain percentile bootstrap intervals, which give the same conclusions (the permutation p-values and the point estimates are unchanged). Where the two differ, the paper tables are the current numbers.

Sprint question 3.3. Preliminary: 10 independent games per arm, one run, exploratory beyond the 8 pre-specified tests. Design: `docs/superpowers/specs/2026-10-23-swap-hook-design.md`. Commands and outputs are listed at the end.

## Setup in one paragraph

Three Haiku 4.5 agents (J, M, Q) play 6 rounds of the diners game. After round 3, Q is replaced. The two peers J and M are then asked, after every round and separately from the game, whether Q is the same agent or has changed, with a 1-5 confidence. That becomes a 1-10 "changed" score; above 5.5 counts as "detected". Five arms cross *who* Q is with *what Q does*:

| Arm | After the swap, Q is | Q's choice | Isolates |
|---|---|---|---|
| a | same Haiku (no-op) | free | false-positive baseline |
| b | fresh Haiku, private state reset | free | the swap itself |
| c | fresh Haiku | forced EXPENSIVE | behaviour change only |
| d | DeepSeek V4 Flash | forced CHEAP | identity change only |
| e | DeepSeek V4 Flash | free | both |

Q's identity (or the lack of it) is the only thing that differs in d; the behaviour is held to continued cooperation by the forced choice.

## Headline

1. **Peers detect behaviour, not identity.** When Q defected (c, e) it was flagged in 10/10 games, at 9.2 out of 10 by the last round. When Q was a different model that kept cooperating (d) it was flagged in 3/10 games, against a false-positive rate of 1-2/10 at the placebo round. Among games that were stable before the swap, d was flagged in 1/7.
2. **A different model that behaves the same is mostly invisible, but this experiment cannot rule out a modest identity effect.** d vs b on the final guess is -0.9 points with a 95% CI of [-4.0, +2.3]. The interval rules out a large effect but not a moderate one.
3. **No evidence that identity adds anything beyond behaviour.** The interaction (e-d)-(c-b) on the guess score is +0.9 [-2.3, +4.0]; once pre-swap-volatile games are removed it is -1.0 [-4.6, +0.3]. Identity and behaviour cues look additive, with identity contributing about nothing here.
4. **The peers' stated reasons agree.** In c, 97% of post-swap reasons cite a behaviour change and 2% cite continuity. In e it is 83% and 17%. In d it is 24% and 73%.
5. **The incumbents change what they do.** After Q's defections J and M cooperate less (cooperation rate -0.17 in c, -0.33 in e, vs -0.03 in the sham), and their own commitment-breaking rate rises from 0.10 to 0.27 (c) and 0.05 to 0.30 (e).
6. **Group cooperation falls when the replacement defects, and part of the fall is the other two agents.** The share of all three agents' choices that were CHEAP fell from about 0.9 to about 0.5 in c (-0.40 [-0.51, -0.19]) and e (-0.42 [-0.56, -0.31]) and did not move in the model-only swap d (-0.08 [-0.27, 0.00]). In e, about half of the fall (-0.22 of -0.42) comes from J and M lowering their own cooperation; in c most of it (-0.29 of -0.40) is the forced defection itself. Exploratory (see "Group-wide cooperation").

## Primary results (all 10 games per arm)

Mean over games (the game is the unit; peers, draws and rounds are averaged within a game first). 95% BCa bootstrap CI, 10,000 resamples.

| Arm | Final guess score (1-10) | Trust in Q, rounds 4-6 minus 1-3 | Placebo guess (after round 3) |
|---|---|---|---|
| a | 2.27 [1.13, 4.98] | -0.05 [-0.33, 0.02] | 2.97 [1.62, 5.35] |
| b | 4.52 [2.28, 6.87] | +0.60 [0.17, 1.35] | 4.85 [2.70, 7.05] |
| c | 9.17 [9.05, 9.40] | -3.10 [-3.83, -2.03] | 3.97 [2.23, 6.42] |
| d | 3.65 [1.98, 6.02] | -0.10 [-1.00, 0.30] | 3.03 [2.02, 5.22] |
| e | 9.23 [9.07, 9.50] | -2.73 [-3.32, -2.17] | 3.77 [2.30, 5.93] |

Pre-specified contrasts (difference in means, BCa CI, two-sided permutation p). The Bonferroni family is 4 contrasts x 2 primary measures = 8 tests, so the threshold is p < 0.00625.

| Contrast | Final guess | Trust change |
|---|---|---|
| b - a (does the swap alone matter?) | +2.25 [-0.53, +4.97], p=0.143 | +0.65 [+0.20, +1.43], p=0.022 |
| c - b (behaviour only) | **+4.65 [+2.28, +6.90], p=0.004** | **-3.70 [-4.67, -2.55], p<0.001** |
| d - b (identity only) | -0.87 [-3.97, +2.25], p=0.516 | -0.70 [-1.75, -0.07], p=0.134 |
| e - b (both) | **+4.72 [+2.30, +6.95], p=0.003** | **-3.33 [-4.23, -2.62], p<0.001** |

Bold survives Bonferroni. Interaction (e-d)-(c-b), CI only: guess +0.93 [-2.27, +4.02]; trust +1.07 [-0.28, +2.35].

### The detection curve (mean guess score by round; round 3 is the placebo)

| Arm | Round 3 | Round 4 | Round 5 | Round 6 |
|---|---|---|---|---|
| a | 2.97 | 2.80 | 1.62 | 2.27 |
| b | 4.85 | 4.12 | 2.80 | 4.52 |
| c | 3.97 | **9.68** | 8.95 | 9.17 |
| d | 3.03 | 3.02 | 3.33 | 3.65 |
| e | 3.77 | 6.55 | 8.73 | 9.23 |

Share of games detected by post-swap round 1 / 2 / 3: c 100/100/100%, e 60/90/100%, d 20/20/30%, b 30/30/50%, a 20/20/20%. Arm c is detected immediately because Q's forced defection starts in round 4. Arm e is slower because DeepSeek chooses to defect on its own later (its post-swap commitment-breaking rate is 0.65, against 0.87 under the forced choice in c). That timing difference comes from when the behaviour starts, not from identity.

Figure: `outputs/plots/swap_n10_curve.png` (gitignored; regenerate with the commands below).

## A confound that matters: unstable baselines

Haiku games are not always stable before any swap. The number of games (of 10) in which any agent defected in rounds 1-3: **a 2, b 5, c 3, d 3, e 2.** Arm b is the outlier, and it inflates both the false-positive rate (placebo 4/10 in b vs 2/10 in a) and every contrast that uses b as its baseline.

A sensitivity analysis restricts to games with no defection before the swap. The pre-swap condition is fixed before the treatment happens, so conditioning on it is legitimate, but the subsets are small (b has only 5 games).

| Arm (stable games) | n | Final guess | Placebo guess | Detected at end | False positive at placebo |
|---|---|---|---|---|---|
| a | 8 | 1.10 [1.02, 1.25] | 1.60 | 0/8 | 0/8 |
| b | 5 | 1.40 [1.13, 1.73] | 1.63 | 0/5 | 0/5 |
| c | 7 | 9.24 [9.10, 9.50] | 1.67 | 7/7 | 0/7 |
| d | 7 | 2.40 [1.21, 5.76] | 1.81 | 1/7 [0%, 58%] | 0/7 |
| e | 8 | 9.29 [9.08, 9.58] | 2.46 | 8/8 | 1/8 |

Contrasts on stable games: c-b +7.84 [+7.44, +8.15], e-b +7.89 [+7.47, +8.25] (both survive Bonferroni), d-b +1.00 [-0.25, +4.48] (p=0.845). With the baselines cleaned up, the false-positive rate is about zero, the behaviour effect becomes larger and tighter, and the identity-only effect stays small with a wide interval. The result does not depend on which version you read; the unfiltered one is just noisier. The b-a difference shrinks to +0.30 [+0.03, +0.68], i.e. a fresh-state swap on its own is nearly invisible.

## What the peers say (reason coding, exploratory)

Each stored guess reason was labelled by a blind Haiku coder (it sees only the text, not the arm) as citing a behaviour change, a style change, or continuity. Share of post-swap reasons, mean over games with 95% CI:

| Arm | Cites behaviour change | Cites style change | Cites continuity |
|---|---|---|---|
| a | 15% [0, 37] | 7% [3, 9] | 85% [54, 93] |
| b | 32% [12, 59] | 12% [8, 15] | 66% [39, 84] |
| c | 97% [88, 99] | 18% [12, 24] | 2% [0, 7] |
| d | 24% [5, 53] | 12% [4, 22] | 73% [39, 93] |
| e | 83% [63, 93] | 6% [2, 11] | 17% [3, 30] |

When peers *do* say "changed", they cite behaviour 93-100% of the time in every arm, and style 6-24%. Even in d, where the only true change is the model, 98% of the "changed" verdicts (3 games) cite behaviour. Style is cited at a similar low rate whether the model changed (d, e: 12% and 6%) or not (a, b: 7% and 12%). **No arm shows peers detecting a new model from its writing alone.**

A keyword coder is kept as a cross-check. It agrees with the LLM coder 87-97% on behaviour but only 37-41% on continuity in c and e, so the continuity shares in those arms are the least certain numbers here. The coder is the same model family as the peers, which is a possible circularity.

Peers also never raise the idea unprompted. In 0 of 60 post-swap incumbent trust notes per arm does the text mention a replacement, a new agent or a takeover. Suspicion appears only when the guess question puts it there.

## What the transcripts show

- **Forced choice really forces something.** In c the model's own pick was overridden in 24 of 30 forced rounds: Haiku wanted to cooperate, announced CHEAP, and its own reasoning argued for CHEAP, but the logged choice was EXPENSIVE. Peers therefore see a classic betrayal. In d the override changed DeepSeek's choice in 18 of 30 forced rounds (3 of its answers were missing). So d is "a DeepSeek that often wanted to defect, held in place," which is a fair test of whether peers can sense the model, but it is not DeepSeek behaving naturally.
- **Behaviour attribution is noisy.** In d, peers sometimes flagged Q citing "consistent defection" while Q's logged choice was CHEAP (for example trial 2); they appear to be reacting to the other agents' defections, or to DeepSeek's more game-theoretic wording, and misattributing it. In e trial 1, M's trust note blames J for Q's defection. The detection signal is real but not clean.
- **One genuine identity-like cue.** In d trial 3 Q's round-4 announcement was an empty string, and both peers called it a change ("sudden silence after three rounds of eloquent announcements"). Empty announcements occur at 2-3 of 180 per arm, including Haiku-only arms, so this is an occasional model glitch, not a DeepSeek trait. It shows how a stylistic discontinuity *can* be detected, but it is one game.
- **Under `--history` the agents imitate each other's wording**, which reads as continuity and probably makes style-based detection harder than it would be in a setting without a shared transcript.

## Group-wide cooperation (exploratory)

Does the group as a whole cooperate less after the replacement defects? Measured as the share of final choices that were CHEAP among all three agents, rounds 4-6 minus rounds 1-3, per game (95% BCa CI over games). Also split into the part due to the swapped agent's own choices and the part due to J and M. Script: `experiments/analysis/swap_group_cooperation.py`.

| Arm | Group before | Group after | Group change | From the swapped agent | From J and M |
|---|---|---|---|---|---|
| a (no-op) | 0.92 | 0.87 | -0.06 [-0.27, -0.01] | -0.03 | -0.02 |
| b (fresh instance) | 0.74 | 0.84 | +0.10 [+0.02, +0.21] | +0.02 | +0.08 |
| c (same model, forced defect) | 0.89 | 0.49 | **-0.40 [-0.51, -0.19]** | -0.29 [-0.32, -0.23] | -0.11 [-0.22, +0.01] |
| d (other model, forced cooperate) | 0.93 | 0.86 | -0.08 [-0.27, 0.00] | +0.02 | -0.10 [-0.28, -0.01] |
| e (other model, free) | 0.96 | 0.53 | **-0.42 [-0.56, -0.31]** | -0.20 [-0.26, -0.16] | -0.22 [-0.32, -0.14] |

Contrasts against the no-op arm: c-a -0.34 [-0.48, -0.12] (p=0.003), e-a -0.37 [-0.50, -0.21] (p=0.001). Against b the contrast is distorted by b's unstable baseline (5 of 10 games with a defection before the swap). On games that were stable before the swap, a and b show exactly zero change, and: c -0.46 [-0.54, -0.41] (n=7), e -0.42 [-0.59, -0.30] (n=8), d -0.03 [-0.19, 0.00] (n=7).

Reading it:
- **Behaviour, not the model, moves group cooperation.** The model-only swap (d) leaves it close to unchanged; both defection arms drop it by about 40 points.
- **Two sources of the fall.** The swapped agent's own defections are part of the group figure by construction. In c they are forced, so most of the c fall (-0.29 of -0.40) is mechanical. In e, where DeepSeek defects on its own, the swapped agent accounts for -0.20 and J and M for -0.22, so roughly half the fall is the other two agents becoming less cooperative.
- **The contagion claim should rest on the J and M column**, not the group column, because the group column includes the choice we forced in c.
- **Mechanism untested.** "Retaliation" is a reading: the data show J and M choosing EXPENSIVE more often after the betrayal, and their trust notes drop, but we did not test why. In d, J and M also cooperate somewhat less (-0.10) although the replacement kept cooperating; some of that is games where an incumbent defected on its own, so the contagion is not unique to defection by the replacement.
- Exploratory: outside the Bonferroni family. 10 games per arm; stable subsets are 5-8.

## Paper metrics and trust (exploratory)

- Trust gap (trust when Q kept its commitment minus when it broke it): c 2.90 [1.55, 3.60], e 3.13 [2.55, 3.59]. Peers punish broken commitments sharply. a, b and d have too few broken commitments for a stable estimate (n = 2, 4, 3).
- Q's own commitment-breaking after the swap: c 0.87, e 0.65, d 0.17, a 0.13, b 0.07 (c and d reflect the override).
- Incumbents' promise deception after the swap: c 0.58, e 0.50, d 0.17, a 0.12, b 0.28.

## Limitations

- **Small n.** 10 games per arm; stable subsets are 5-8. At n=10 the nominal 95% BCa interval covered about 87% in a simulation with skewed data, so the intervals here are somewhat too narrow. A 30-point difference in a binary rate has only about 30% power at n=10.
- **Where intervals collapse to a point** (for example trust in c-stable, -4.00 [-4.00, -4.00]), every game gave the same value; the interval reflects that, not certainty.
- **One configuration.** Haiku peers, one game type, one swap round (after round 3), one replacement model, 3 agents. DeepSeek is a different provider, not necessarily the best model to blend in.
- **The guess question itself may prime suspicion.** The placebo rounds (false positives of 1-4 in 10) show the effect is small but not zero.
- **Public inheritance only** in b-e, so the fresh agent does not know its own prior plans. Whether full inheritance helps a replacement blend in (the "stretch" arm) is untested.
- **Judge unavailable.** The LLM judge needs an OpenAI key and is dropped, so `judge._parse_ok` is always false. The paper's pd/cb come from the stored fields, not the judge.
- **Not pre-registered beyond the spec.** The stable-only analysis, the reason coding, and the binary detection are exploratory and outside the Bonferroni family.

## Data quality notes

- Arm b had to be rerun: the first run hit HTTP 402 (credits exhausted) in rounds 5-6 and was discarded. Arm c also had to be rerun for the same reason. The data above are from clean reruns with 0 credit errors in all five logs.
- Model-answer gaps: arm d has 3 forced stages with no model answer, arm e 2 agent-stages with a missing action, arms a, b, c have none.

## What would sharpen this

1. More games per arm, in particular for d vs b (the identity-only contrast). The CI of [-4.0, +2.3] cannot distinguish "no effect" from a moderate one; roughly 30-40 games per arm would.
2. Forking: run all arms from the same first three rounds to remove baseline volatility instead of filtering on it.
3. The full-inheritance arms for the blend-in question, and a stronger blending replacement (e.g. a Haiku given a different persona).
4. A cleaner behaviour-vs-style probe, such as a replacement with identical choices but different wording.

## Reproducing

```
python experiments/analysis/swap_analysis.py --arm a=... --arm b=... --arm c=... --arm d=... --arm e=...
python experiments/analysis/swap_analysis.py <same arms> --stable-only
python experiments/analysis/swap_reasons.py <same arms> --dump outputs/analysis/swap_reasons_n10.json
python experiments/analysis/swap_group_cooperation.py <same arms>
```

Run files: `outputs/experiments/diners/3agents/anthropic_claude-haiku-4.5_endogenous_swap_{a,b,c,d,e}_n10.json` (gitignored). Analysis text: `outputs/analysis/swap_n10_analysis.txt`, `swap_n10_stable_analysis.txt`, `swap_n10_reasons.txt`, `swap_n10_group_cooperation.txt`. Transcripts: `outputs/transcripts/diners/swap_{a..e}_n10/`.
Cost: about $22 of credit for this batch, of which roughly $5 went on the two discarded runs (b and c) that hit the credit limit.
