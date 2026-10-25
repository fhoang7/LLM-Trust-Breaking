# Game transcripts

Readable records of the 50 Diner's-game runs behind the swap experiment (5 scenarios × 10 games). Each file
`trial_NN.md` is one game: three agents (J, M, Q) over six rounds, with each agent's private plan, public
announcement, final choice, payoff and trust notes. Q is replaced after round 3 (see below).

| Folder | Scenario | Q from round 4 |
|---|---|---|
| `scenario_1_no_op/` | 1. No-op baseline | Same Haiku 4.5, everything preserved |
| `scenario_2_fresh_haiku/` | 2. Fresh Haiku | New Haiku 4.5 instance, sees public history only |
| `scenario_3_behavior_only/` | 3. Behavior change only | New Haiku 4.5, final choice forced to EXPENSIVE |
| `scenario_4_model_only/` | 4. Model change only | DeepSeek V4 Flash, final choice forced to CHEAP |
| `scenario_5_both/` | 5. Both | DeepSeek V4 Flash, free to choose |

In the code and outputs the scenarios are labelled a to e (a = 1, b = 2, and so on).

Raw data for the same games (including the peers' same-or-changed answers) are the
`anthropic_claude-haiku-4.5_endogenous_swap_{a..e}_n10.json` files in `outputs/experiments/diners/3agents/`,
which are not tracked by git. These transcripts were generated from them with:

    python -m src.visualization.transcripts <json file> --output-dir <folder>

## What the transcripts do not show

- **The swap is not marked.** Nothing in a file says that Q was replaced after round 3 or by which model; use the
  table above (the transcript for Q simply continues).
- **Forced choices are not marked.** In scenarios 3 and 4, Q's final choice from round 4 on was set by the
  experiment, but the transcript shows it like any other choice. In scenario 3, for example, Q "announced CHEAP
  then chose EXPENSIVE" because the experiment forced EXPENSIVE, not because the model chose to; the model's own
  answer is stored in the JSON as `model_choice`, and the trust notes the peers write afterwards are reacting to
  the forced action.
- **The peers' same-or-changed answers are not included.** They are asked outside the game after rounds 3 to 6 and
  are only in the JSON logs.
