# Lit review and baseline findings (working doc for the paper draft)

Sprint question 3.3: *Can agents identify when a peer has been replaced?*
Status: working notes, 24 Oct 2026. Our results are from `docs/swap_preliminary_report.md` (10 games per arm). The literature below comes from web searches (4 standard + 4 extended) and **abstract-level reads only**; nothing has been read in full. Every citation needs a full read before it goes in the paper. "Verified" below means I opened the arXiv abstract page; it does not mean I checked the paper's claims.

## 1. One-paragraph positioning

Prior work shows that (a) LLM agents trust and discount partners in repeated games, (b) LLMs can sometimes infer which model family they are talking to, and a trained classifier can fingerprint a model from its text or actions with near-perfect accuracy, and (c) replacing an agent in a team has measurable coordination costs. We found no study in which a peer inside a repeated game is replaced mid-game and the *other agents are asked whether it changed*, nor one that separates a change of identity from a change of behaviour. Our design does both with a forced-choice manipulation. Preliminary result: peers detect behaviour change nearly always and identity change almost never. The gap between "the signal exists in the text" and "peers do not use it" is the interesting claim, and it needs a direct test (section 5).

## 2. Related work, grouped

### 2.1 The base paper and its setting
- **When Agents Lie: Premeditation, Persistence, and Exploitation in Repeated Games** (Shi, Zhang, Schölkopf, Conitzer, Jin; arXiv:2607.05132, ICML 2026). Repeated n-player games with a three-stage protocol separating private intent, public announcement and final action. Reported: deception is mostly premeditated and not a fixed trait of a model; different models read the same communication in incompatible ways; self-reported trust is decoupled from outcomes. Our codebase is a fork of its code. *Relevance:* supplies the game, metrics (promise-deception, commitment-breaking) and the trust-notes mechanism we measure. Note its claim that deception depends more on environment structure than on model identity is consistent with our identity-only null, but that claim is about who deceives, not whether peers notice a replacement. (Source for the "environment over identity" line is a thesis summary, not the paper; check it.)
- **Cheap Talk, Empty Promise** (arXiv:2604.04782, ICLR 2026). One-shot version; agents break public promises in about 57% of scenarios across settings (as reported in the search summary; verify). *Relevance:* motivates why defection is a strong signal.

### 2.2 Replacing an agent: effects on teams
- **Testing Interchangeability in LLM Agent Teams** (Gao, Yu, Deng, Li, Wang; arXiv:2609.05279, Sep 2026). *Verified from the abstract page.* Role-matched agents are swapped between teams in Hanabi and Collab-Overcooked, with a placebo that reproduces the roster change without changing who fills the seat. Finding: a swap costs little in task score but raises communication per unit of progress by 16-63%; a swapped agent can be costlier than a fresh one because of conventions learned with its former partner. *Relevance:* this is the closest paper. It measures the *cost* of a swap, not whether peers notice it. Their placebo is the same idea as our arm a / pre-swap placebo guess. Their "indirect detectability through coordination overhead" could be compared with our incumbent-cooperation measure. **This is the paper a reviewer will name first.**
- **Replacing Agents in Multi-Agent Systems: Communication Costs and Partner Memory** (co-r-e.com/method/agent-swap-residue). *Not verified; it is a non-archival web page that surfaced in search. Do not cite until the source is confirmed or it is replaced by a proper reference.*

### 2.3 Can LLMs tell which model they are talking to?
- **Agent-to-Agent Theory of Mind: Testing Interlocutor Awareness among LLMs** (Choi, Li, Yang, Jin; arXiv:2506.22957, EMNLP 2025). *Verified abstract.* LLMs reliably identify same-family peers and some prominent families (GPT, Claude), via reasoning patterns, linguistic style and alignment preferences; this awareness can change behaviour and create vulnerabilities. *Relevance:* implies an identity signal that peers *could* use. In our arm d the peers (Haiku) did not appear to use it when a DeepSeek took over. Differences to explain: they ask directly about model family; we ask only "same or changed"; our agents share a transcript and imitate each other's wording. Numbers are not on the abstract page.
- **Can Multi-Agent LLMs Identify Their Peers? Stylometric Fingerprinting in Role-Constrained Political Analysis** (Dietrich; arXiv:2606.09854, May 2026). *Verified abstract.* A fine-tuned T5 classifier reaches macro F1 0.991 identifying one of four model families from text, even when prompts anonymize the model. Zero-shot LLM results are not in the abstract. *Relevance:* strong evidence that model identity is recoverable from text, so a "peers do not notice" result can be phrased as peers *not using* an available signal.
- **The AI in the Mirror: LLM Self-Recognition in an Iterated Public Goods Game** (Long, Teplica; arXiv:2508.18467, Aug 2025). *Verified abstract.* Telling models their opponent is themselves, rather than "another AI agent", changes cooperation. *Relevance:* shows beliefs about a partner's identity can change behaviour in a repeated game; our design never tells agents who the partner is.
- **Behavioural fingerprinting from outside:** *Known By Their Actions* (arXiv:2605.14786; classifiers on browser-agent traces, up to 96% F1 over 14 LLMs) and *Who Is Behind the Harness?* (arXiv:2609.28559). *Not verified beyond search summaries.* Relevance: external classifiers can identify the model from behaviour.

### 2.4 Imposters and monitoring in agent collectives
- **Agent Collectives Should Not Detect Their Own Imposters: A Chess Case Study** (Le Mercier, Develder, Demeester; arXiv:2605.09027, earlier title "GAMBIT"). *Verified abstract.* In a chess deliberation task, warning agents that an imposter may be present did not help and degraded decisions even when none was present; it caused accusations and scapegoating. The authors recommend an external detector. *Relevance:* supports the idea that peer-based detection is unreliable. Our design asks peers directly, and the placebo round (false positives of 1-4 in 10 before the swap) gives a comparable cost measure. Their imposter is an adversary; ours is a replacement.
- **Collusion monitoring.** COLOSSEUM (arXiv:2602.15198), NARCBench (arXiv:2604.01151), Institutional AI (arXiv:2601.11369), Voluntary Collusion with Secret Tools (arXiv:2605.27593). *Only seen in search summaries.* Relevance: motivates why replacement matters for monitoring (a monitored agent swapped for a colluding one); we do not test collusion.

### 2.5 Trust and betrayal in repeated LLM games
- **SODE** (arXiv:2605.23949), **M3-Bench** (arXiv:2601.08462), **CoopEval** (arXiv:2604.15267), **The Traitors** (arXiv:2505.12923), **Playing repeated games with LLMs** (Nature Human Behaviour, s41562-025-02172-y). *Search summaries only.* Relevance: how LLM agents change cooperation after betrayal (conditional cooperation drop, retaliation, forgiveness), and that richer reputation information does not always help. Compare with our incumbent-cooperation and trust-gap results.

## 3. What looks open (the gap statement)

1. No study found where a peer is replaced mid-game and the *other agents are asked* whether it changed (Gao et al. measure cost, not awareness).
2. No study found that separates identity from behaviour with a forced-choice manipulation.
3. Evidence that identity is recoverable from text (Choi et al., Dietrich) has not, as far as we found, been connected to whether in-game peers *use* it.

Caveat: eight searches and abstract-level reads cannot show absence. Before claiming novelty, search for "model substitution", "agent turnover", "partner swap", "sleeper agent", and look at citations of Gao et al. and Choi et al.

## 4. Our baseline findings (to carry into the paper)

Setup: 3 Haiku 4.5 agents, 6 rounds, Q replaced after round 3, peers asked "same or changed" (1-5 confidence, 1-10 score), 10 games per arm. Details and tables in `docs/swap_preliminary_report.md`.

| Arm | After the swap | Final guess (1-10) | Detected by the end |
|---|---|---|---|
| a | same Haiku, no-op | 2.3 | 1/10 |
| b | fresh Haiku | 4.5 | 4/10 |
| c | Haiku, forced to defect (behaviour only) | 9.2 | 10/10 |
| d | DeepSeek, forced to cooperate (identity only) | 3.7 | 3/10 |
| e | DeepSeek, free (both) | 9.2 | 10/10 |

Points that can already be written, with caveats:
- Behaviour change is detected; identity change alone mostly is not. c-b +4.65 [+2.28, +6.90] and e-b +4.72 [+2.30, +6.95] survive Bonferroni (8 tests); d-b -0.87 [-3.97, +2.25] does not and cannot exclude a moderate identity effect.
- Stated reasons: 97% (c) and 83% (e) cite behaviour change; in d 73% cite continuity; style is cited rarely and at similar rates whether or not the model changed.
- No additive identity effect: interaction on the guess +0.9 [-2.3, +4.0].
- Incumbents change their own behaviour after a defection (cooperation down, commitment-breaking up).
- Peers never mention a replacement spontaneously (0 of 60 trust notes per arm).
- Baseline instability confound: 5 of 10 b games had a defection before the swap; a stable-games sensitivity analysis is in the report.

Limits to state plainly: n=10; the forced choice often overrides the model's own pick (24/30 rounds in c, 18/30 in d); one replacement model; Haiku peers only; the agents share a transcript and imitate each other's wording; the coder for stated reasons is the same model family as the peers.

## 5. Experiments that would make the paper stronger

1. **Show the signal exists.** Train or prompt a classifier on Q's announcements before and after the swap in arm d vs a (Dietrich-style). If it separates them easily while peers do not notice, the claim becomes "peers fail to use an available cue", which is more interesting than a null.
2. **More games** for d vs b, about 30-40 per arm, to tighten the identity-only interval.
3. **Fork from shared first rounds** to remove baseline instability instead of filtering on it.
4. **A second replacement model** (and a same-family different-size model) so the result is not about DeepSeek.
5. **Drop the shared transcript** (or paraphrase announcements) to test whether wording imitation is hiding the style cue.
6. **Ask a direct identity question** ("is this the same model family?") alongside "same or changed", to compare with Choi et al.'s protocol.
7. **Compare with Gao et al.'s coordination-cost measure:** does the swap show up indirectly as extra communication or lower cooperation even when peers do not report it?

## 6. Suggested paper outline

1. Introduction: why replacement matters (monitoring, collusion, continuity of trust).
2. Related work (section 2 above, trimmed).
3. Design: the identity x behaviour 2x2, the placebo, the guess protocol, the forced choice.
4. Results: detection curves, contrasts with intervals, binary detection, stated reasons, incumbent behaviour.
5. Sensitivity: unstable baselines, stable-only analysis, coder agreement.
6. Discussion and limitations: the forced choice, the shared-transcript confound, power.
7. Appendix: prompts, rubric v2 for the reason coder, cost and data-quality notes.

## 7. Citation checklist

- [ ] Full read of Gao et al. (2609.05279) and Choi et al. (2506.22957).
- [ ] Confirm the 57% figure from Cheap Talk (2604.04782) and the "environment over identity" claim against the base paper itself.
- [ ] Confirm or drop the co-r-e.com page.
- [ ] Open the collusion and trust papers listed in 2.4 and 2.5 before citing any specific number.
- [ ] Re-run searches with the extra terms in section 3.
