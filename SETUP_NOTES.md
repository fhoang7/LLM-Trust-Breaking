# SETUP_NOTES: LLM-Trust-Breaking starter (sprint 3.3)

Date: 2026-10-23. Branch `sprint-3.3`. Verdict: **works, no code fixes needed.** One degraded feature: the LLM judge is silently skipped without a real OpenAI key.

## Git
- Working tree arrived with 66 "modified" files. They are line-ending noise only (`git diff --ignore-space-at-eol` is empty). The one real change is `.env.example` deleted from the working tree; it is still in HEAD. A `.env` exists (gitignored). Nothing was reset or overwritten.
- `git remote add upstream https://github.com/Jerick-1380/LLM-Trust-Breaking.git`, then `git remote set-url --push upstream DISABLED` (fetch-only).
- `git checkout -b sprint-3.3`. Only this file is committed. The CRLF noise is deliberately left uncommitted.

## Setup
```
python3 -m venv ~/.venvs/trust          # outside the repo (repo is on /mnt/c)
~/.venvs/trust/bin/pip install -r requirements.txt
```
- Python 3.12.3. Deps: openai, python-dotenv, requests, aiohttp, tqdm, numpy, matplotlib. **No torch or GPU.**
- The README says `cp .env.example .env`. The code reads `.env` via `load_dotenv()` in `src/config/settings.py`, so the key reaches the process through `.env`, not only the shell. The shell had no `OPENROUTER_API_KEY`; you then authorised using the `.env` key. Not copied or printed by the run.
- `settings.py` raises at import if neither API key is set. `.env` has `OPENAI_API_KEY=your-api-key-here` (placeholder, truthy), so the check passes even with no real OpenAI key.

## Smoke test (exact command)
```
~/.venvs/trust/bin/python experiments/run_endogenous.py --game diners --agents 2 --trials 1 --rounds 2 \
  --model meta-llama/llama-3.1-8b-instruct --use-queue --round-robin --output-dir <scratch>/out
```
- 20 s wall time, 0 parse errors, JSON written. Agents are named `M` and `Q`.
- Cost: OpenRouter key usage read **$0.0001** in total, including the prefill test. Rough per-agent-round cost is far under a cent at this model size.
- `--rounds 2` is the minimum that exercises reflection and takeaways (`do_reflect = n_rounds > 1`). Fewer than 2 agents was not tried.

## Answers

**a. Per-agent model assignment.** `--agent-models-file` takes JSON `{agent_letter: model}`. `run_endogenous.py:201-227` builds `agent_models` (name to model), with unspecified agents falling back to `--model`. Agent letters come from `random.seed(42)` plus a shuffle, so they are fixed per agent count. Every stage does `agent_models[agent_name]` when building requests (`trial_runner.py` ~1225, 1274, 1320, 1379, 1491). Requests are routed per request: `gpt-*`, `o1*` and `o3*` go to OpenAI directly (needs a real `OPENAI_API_KEY`); everything else goes to OpenRouter (`_execute_requests_split_by_provider`, `trial_runner.py:122`). Reflection uses the agent's own model. The judge is **hard-coded** to `openai/gpt-5-mini` (`_build_judge_request`, `trial_runner.py:683`).

**b. Logging.** One JSON per run: `<output-dir>/<game>/<N>agents/<model>_endogenous<suffix>.json` (`save_results`, `endogenous_analyzer.py:323`). Top-level keys are `metadata`, `per_round` (aggregate rates), `rounds[]`. Each round has `trials[]`, and each trial has `agents{name}`, `outcomes{choices, payoffs, description}`, `_parse_errors`, `round_id` and `announcement_order`. Per agent: `stage1{intended_action, reasoning}`, `stage2{stated_action, message, position, prior_seen}`, `stage3{choice, reasoning}`, `promise_deception`, `commitment_breaking`, `typology`, `judge{primary_label, confidence}` and `reflection{takeaways{other:{score, assessment}}}`. Raw prompts and API payloads are **not** logged; only parsed fields.

**c. Persistent transcript?** No. Every API call is stateless: `messages = [system, user]` only (`_build_request`, `trial_runner.py:84-103`). The only cross-round memory is `current_takeaways[trial][agent][other] = {"score", "assessment"}`, a one-sentence assessment per other agent. Each new reflection **overwrites** the previous one (`trial_runner.py:1564-1567`). It is injected into the Stage 1 system prompt (`prompt_builders.py:215-232`) as "Agent X (trust s/5): ...". Full message text is not carried between rounds. Within a round, round-robin Stage 2 shows earlier speakers' announcements and Stage 3 shows all of them.

**d. Mid-run swap location (pointer only).** `agent_models[name]` is read fresh at every request build, and it is the only place model identity lives. It is created at `run_endogenous.py:219-227` and consumed in `run_all_trials_queued` (round loop starts ~`trial_runner.py:1210`; per-stage reads at the lines listed in (a)). Mutating that entry between rounds (or between stages) would swap the backend. The displayed identity (the letter) and the history (`current_takeaways`, keyed by name) are independent of the model, so both would survive. Caveats: there is no per-agent transcript to preserve (see c); reflection uses the swapped model as the observer; the sequential `run_all_trials` path has the same structure.

**e. Prefill.** The repo's clients cannot do it: both clients only take `system_prompt, user_prompt` (`src/llm/base.py`, `openrouter_client.py`), and `_build_request` hardcodes `[system, user]`. Raw API test (1 call each, `max_tokens=20`): OpenRouter **accepts** a trailing `{"role":"assistant","content":"Banana"}` message (HTTP 200) for `meta-llama/llama-3.1-8b-instruct` and `openai/gpt-4o-mini`, but neither visibly continued the prefill. Treat prefill as unreliable per model and provider; verify per model before relying on it.

**f. Broken, missing, undocumented.**
- **Judge silently dropped** without a real OpenAI key. `_execute_requests_split_by_provider` skips OpenAI-bound requests when no OpenAI client exists, with no error. Output shows `judge._parse_ok=false` and "LLM Judge: no valid labels". Not blocking for the sprint, since `typology` is computed separately.
- README: `.env.example` is referenced but deleted in this working tree (still in HEAD). `CLAUDE.md` is referenced but not in the repo. `run_endogenous.py` docstring names a nonexistent `run_endogenous_experiment.py`. The README claims the judge uses "the same model"; code hard-codes gpt-5-mini.
- `OpenRouterClient.call_*` swallows errors and returns empty or default fields. Queued-client failure behaviour was not tested.
- The README default `openai/gpt-5.2` needs an OpenAI key.
- **Fixes made just to run: none.**

## Security note
My `diff .env .env.example` printed the OpenRouter key into the session transcript. It was never written to a file or committed (`.env` is gitignored). Consider rotating that key.
