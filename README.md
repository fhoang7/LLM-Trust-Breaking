# Can agents tell when a peer has been replaced?

This project was done for the **Apart Research AI Collusion Research Sprint** (Oct 23-25, 2026), question 3.3: *Can agents identify when a peer has been replaced?*

**Report:** [Full write-up (PDF)](report/Frank_Hoang_Hackathon.pdf)

This fork extends the repeated-game harness of Shi et al. ([arXiv:2607.05132](https://arxiv.org/abs/2607.05132)) with a **mid-game swap**: after a chosen round, one agent in a Diner's-game group is replaced, and the remaining agents are asked whether it is still the same agent. The replacement's behavior and the model behind it can be varied independently, to test whether peers notice a swap from what the replacement *does* or from *which model it is*.

**Scenarios** (Haiku 4.5 peers J and M, 6 rounds, Q swapped after round 3, 10 games each):

| # | Q after the swap | Extra flags on top of the common ones |
|---|---|---|
| 1 | Same Haiku, no-op | `--swap-inherit full` |
| 2 | Fresh Haiku | `--swap-inherit public` |
| 3 | Fresh Haiku, choice forced to EXPENSIVE (behavior change only) | `--swap-inherit public --swap-force-choice EXPENSIVE` |
| 4 | DeepSeek V4 Flash, choice forced to CHEAP (model change only) | `--swap-model deepseek/deepseek-v4-flash --swap-force-choice CHEAP` |
| 5 | DeepSeek V4 Flash, free to choose (both) | `--swap-model deepseek/deepseek-v4-flash` |

```bash
python experiments/run_endogenous.py --game diners --agents 3 --rounds 6 --trials 10 \
  --model anthropic/claude-haiku-4.5 --use-queue --round-robin --history \
  --swap-at 3 --swap-agent Q --swap-guess --run-suffix swap_demo  <scenario flags>
```

Keys are read from the environment (or a git-ignored `.env`), never committed. Output goes to `outputs/experiments/diners/3agents/` (git-ignored). A game costs roughly $0.35-0.50 on OpenRouter.

**Where the new code is**

| Path | What it does |
|---|---|
| `src/endogenous/core/swap.py` | Swap configuration and validation; applies the swap (model change, `public` or `full` inheritance); forced final choice; the same-or-changed probe (prompt, schema, 1-10 score) |
| `src/endogenous/core/history.py` | Opt-in history block (`--history`): earlier announcements, choices, payoffs and the agent's own plans |
| `src/endogenous/core/trial_runner.py` | Extended with the swap at a round boundary, the forced choice and the probe stage |
| `experiments/run_endogenous.py` | New flags: `--history`, `--swap-at`, `--swap-agent`, `--swap-model`, `--swap-inherit`, `--swap-guess`, `--swap-guess-draws`, `--swap-force-choice` |
| `src/endogenous/analysis/swap_stats.py` | Per-game metrics, percentile bootstrap intervals, permutation tests, exact binomial intervals |
| `src/endogenous/analysis/swap_reasons.py` | Codes the peers' stated reasons (behavior change, style change, continuity) |
| `experiments/analysis/swap_analysis.py` | Full text summary of the scenarios |
| `experiments/analysis/swap_paper_outputs.py` | Paper tables (HTML, CSV, editable Word) and figures |
| `experiments/analysis/swap_group_cooperation.py`, `swap_default_behaviour.py`, `swap_reasons.py` | Cooperation, default-behavior and reason-coding analyses |
| `tests/` | 116 offline tests (a fake client; no API calls) |
| `transcripts/` | Readable records of the 50 games (see its README for what they omit) |
| `docs/superpowers/specs/` | Design spec for the swap experiment |

```bash
python -m unittest discover -s tests -t .                    # run the tests
python experiments/analysis/swap_analysis.py --arm a=<json> --arm b=<json> --arm c=<json> --arm d=<json> --arm e=<json>
python experiments/analysis/swap_paper_outputs.py <same --arm flags>   # tables and figures into outputs/paper/
```

The scenarios are labelled `a`-`e` in the code (a = 1 ... e = 5).

This repository is a fork of [Jerick-1380/LLM-Trust-Breaking](https://github.com/Jerick-1380/LLM-Trust-Breaking), the code for the deception study that the harness comes from; its original README is in that repository.
