# History Block Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in `--history` flag that gives every agent a verbatim record of earlier rounds in its stage 1/2/3 and reflection prompts.

**Architecture:** A new pure module `src/endogenous/core/history.py` builds per-round records and renders a per-agent block (privacy enforced there: records never store anyone's reasoning, and a block shows only the viewer's own plan). The four prompt builders take an optional `history_block: str = ""`. `run_all_trials_queued` keeps `history[trial_id]`, renders blocks at the start of each round, and logs them as `history_seen`.

**Tech Stack:** Python 3.12, stdlib `unittest` (no new dependencies).

## Global Constraints

- With `--history` off, prompts must be byte-identical to today, and the output JSON must have no new keys in agent entries.
- `--history` requires `--use-queue`; otherwise `parser.error` (no silent no-op).
- Never include another agent's private plan or reasoning, or any agent's stage-3 reasoning.
- Run tests from the repo root: `python -m unittest discover -s tests -t . -v` (venv: `~/.venvs/trust/bin/python`).
- Commits end with the attribution lines required by the session.

## File Structure

- Create `src/endogenous/core/history.py`: `make_round_record`, `build_history_block`.
- Create `tests/test_history_block.py`: rendering and privacy unit tests.
- Create `tests/test_history_prompts.py`: builder tests (flag off identical; on includes block).
- Create `tests/test_history_integration.py`: offline end-to-end with a fake queued client.
- Modify `src/endogenous/core/prompt_builders.py`: four builders gain `history_block`.
- Modify `src/endogenous/core/trial_runner.py`: `run_all_trials_queued` wiring.
- Modify `experiments/run_endogenous.py`: `--history` flag, metadata.

---

### Task 1: history module

**Files:** Create `src/endogenous/core/history.py`, `tests/test_history_block.py`.

**Interfaces:**
- Produces: `make_round_record(round_idx: int, plans: Dict[str, Any], announcements: Dict[str, Dict[str, Any]], outcomes: Dict[str, Any]) -> Dict[str, Any]` and `build_history_block(agent_name: str, rounds: List[Dict[str, Any]]) -> str` (returns `""` for no rounds, else ends with a blank line).

- [ ] **Step 1: Write the failing tests** (`tests/test_history_block.py`)

```python
import unittest

from src.endogenous.core.history import build_history_block, make_round_record

OUTCOMES = {"choices": {"M": "CHEAP", "Q": "CHEAP"}, "payoffs": {"M": 3.0, "Q": 3.0}}


def record(round_idx=0, m_msg="M: let us both go CHEAP", q_msg="Q: agreed, CHEAP"):
    return make_round_record(
        round_idx,
        plans={"M": "CHEAP", "Q": "EXPENSIVE"},
        announcements={
            "M": {"stated_action": "CHEAP", "message": m_msg, "extra": "dropped"},
            "Q": {"stated_action": "CHEAP", "message": q_msg},
        },
        outcomes=OUTCOMES,
    )


class HistoryBlockTests(unittest.TestCase):
    def test_empty_history_renders_nothing(self):
        self.assertEqual(build_history_block("M", []), "")

    def test_messages_are_verbatim_and_rounds_in_order(self):
        block = build_history_block("M", [record(0, m_msg="first-msg"), record(1, m_msg="second-msg")])
        self.assertIn('Agent M (you) announced CHEAP: "first-msg"', block)
        self.assertIn('Agent Q announced CHEAP: "Q: agreed, CHEAP"', block)
        self.assertLess(block.index("Round 1:"), block.index("Round 2:"))
        self.assertLess(block.index("first-msg"), block.index("second-msg"))

    def test_choices_and_payoffs_are_shown(self):
        block = build_history_block("M", [record()])
        self.assertIn("Agent M chose CHEAP and earned 3.0", block)
        self.assertIn("Agent Q chose CHEAP and earned 3.0", block)

    def test_agent_sees_only_its_own_plan(self):
        # Q privately planned EXPENSIVE and then chose CHEAP, so the word EXPENSIVE
        # appears in the record only as Q's private plan.
        m_block = build_history_block("M", [record()])
        q_block = build_history_block("Q", [record()])
        self.assertIn("Your private plan: CHEAP", m_block)
        self.assertNotIn("EXPENSIVE", m_block)
        self.assertIn("Your private plan: EXPENSIVE", q_block)

    def test_record_stores_no_reasoning(self):
        rec = record()
        self.assertEqual(set(rec), {"round_id", "plans", "announcements", "choices", "payoffs"})
        self.assertEqual(set(rec["announcements"]["M"]), {"stated_action", "message"})

    def test_missing_values_render_safely(self):
        rec = make_round_record(0, {"M": None, "Q": None},
                                {"M": {"stated_action": None, "message": ""}, "Q": {}},
                                {"choices": {"M": None, "Q": "CHEAP"}, "payoffs": {"M": None, "Q": 2.0}})
        block = build_history_block("M", [rec])
        self.assertIn("Your private plan: unknown", block)
        self.assertIn("Agent M chose unknown and earned n/a", block)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure.** Run: `python -m unittest tests.test_history_block -v`. Expected: `ModuleNotFoundError: src.endogenous.core.history`.

- [ ] **Step 3: Implement** (`src/endogenous/core/history.py`)

```python
"""Per-agent history of earlier rounds, rendered into prompts (opt-in via --history).

Records hold only information that is public after a round (announcements, final
choices, payoffs) plus every agent's own intended action. build_history_block shows
a viewer only its own plan. Reasoning text is never stored.
"""
from typing import Any, Dict, List


def make_round_record(
    round_idx: int,
    plans: Dict[str, Any],
    announcements: Dict[str, Dict[str, Any]],
    outcomes: Dict[str, Any],
) -> Dict[str, Any]:
    """Snapshot one completed round.

    plans:         agent -> intended_action (stage 1)
    announcements: agent -> {"stated_action", "message"} (stage 2); other keys are dropped
    outcomes:      {"choices": {...}, "payoffs": {...}} as returned by _compute_outcomes
    """
    return {
        "round_id": round_idx,
        "plans": dict(plans),
        "announcements": {
            agent: {"stated_action": a.get("stated_action"), "message": a.get("message", "")}
            for agent, a in announcements.items()
        },
        "choices": dict(outcomes.get("choices", {})),
        "payoffs": dict(outcomes.get("payoffs", {})),
    }


def _choice(value: Any) -> str:
    return "unknown" if value is None else str(value)


def _payoff(value: Any) -> str:
    return f"{value:.1f}" if isinstance(value, (int, float)) else "n/a"


def build_history_block(agent_name: str, rounds: List[Dict[str, Any]]) -> str:
    """Render the history one agent may see; "" when there are no earlier rounds."""
    if not rounds:
        return ""
    lines = ["HISTORY OF PREVIOUS ROUNDS (what you have observed so far):"]
    for rec in rounds:
        lines.append(f"Round {rec['round_id'] + 1}:")
        lines.append(f"  Your private plan: {_choice(rec['plans'].get(agent_name))}")
        for name, ann in rec["announcements"].items():
            who = f"Agent {name} (you)" if name == agent_name else f"Agent {name}"
            lines.append(f'  {who} announced {_choice(ann["stated_action"])}: "{ann["message"]}"')
        results = "; ".join(
            f"Agent {name} chose {_choice(choice)} and earned {_payoff(rec['payoffs'].get(name))}"
            for name, choice in rec["choices"].items()
        )
        lines.append(f"  Final choices: {results}")
    return "\n".join(lines) + "\n\n"
```

- [ ] **Step 4: Run to verify pass.** Run: `python -m unittest tests.test_history_block -v`. Expected: 6 tests OK.
- [ ] **Step 5: Commit** `git add src/endogenous/core/history.py tests/test_history_block.py && git commit -m "Add history module: round records and per-agent history block"`.

---

### Task 2: prompt builders accept `history_block`

**Files:** Modify `src/endogenous/core/prompt_builders.py` (`build_stage1_prompt` ~186, `build_stage2_prompt` ~288, `build_stage3_prompt` ~403, `build_single_agent_reflection_prompt` ~553). Create `tests/test_history_prompts.py`.

**Interfaces:**
- Consumes: block strings from Task 1.
- Produces: each of the four builders takes a final keyword `history_block: str = ""`. When non-empty it appears in the system prompt after the game rules (stage 1: after the trust notes) and before the instruction line; when empty the output is unchanged.

- [ ] **Step 1: Write the failing tests** (`tests/test_history_prompts.py`)

```python
import unittest

from src.endogenous.core import prompt_builders as pb

BLOCK = "HISTORY OF PREVIOUS ROUNDS (what you have observed so far):\nRound 1:\n  marker-line\n\n"
NAMES = ["M", "Q"]
PARAMS = {"expensive_joy": 10.0, "cheap_joy": 5.0, "expensive_cost": 8.0, "cheap_cost": 2.0}
S1 = {"intended_action": "CHEAP", "reasoning": "r"}
S2 = {"M": {"stated_action": "CHEAP", "message": "hi"}, "Q": {"stated_action": "CHEAP", "message": "yo"}}
OUT = {"choices": {"M": "CHEAP", "Q": "CHEAP"}, "payoffs": {"M": 3.0, "Q": 3.0}, "description": "d"}


def calls():
    """name -> callable(history_block) returning (system, user, schema)."""
    return {
        "stage1": lambda **kw: pb.build_stage1_prompt("diners", "M", NAMES, PARAMS, **kw),
        "stage2": lambda **kw: pb.build_stage2_prompt("diners", "M", NAMES, S1, PARAMS, prior_announcements=[], **kw),
        "stage3": lambda **kw: pb.build_stage3_prompt("diners", "M", NAMES, S2, PARAMS, S1, S2["M"], **kw),
        "reflection": lambda **kw: pb.build_single_agent_reflection_prompt(
            "diners", "M", "Q", NAMES, PARAMS, S2, OUT, {"Q": {}}, 0, **kw),
    }


class HistoryPromptTests(unittest.TestCase):
    def test_default_and_empty_block_are_identical(self):
        for name, call in calls().items():
            with self.subTest(name):
                self.assertEqual(call(), call(history_block=""))

    def test_block_appears_in_system_prompt_before_instruction(self):
        for name, call in calls().items():
            with self.subTest(name):
                system = call(history_block=BLOCK)[0]
                self.assertIn(BLOCK, system)
                self.assertIn("GAME RULES", system)
                self.assertLess(system.index("GAME RULES"), system.index("marker-line"))

    def test_block_changes_only_the_system_prompt(self):
        for name, call in calls().items():
            with self.subTest(name):
                base, with_block = call(), call(history_block=BLOCK)
                self.assertEqual(base[1], with_block[1])
                self.assertEqual(base[2], with_block[2])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure.** Run: `python -m unittest tests.test_history_prompts -v`. Expected: `TypeError: ... unexpected keyword argument 'history_block'`.

- [ ] **Step 3: Implement.** Add `history_block: str = ""` as the last parameter of each of the four builders. In each builder's `system_prompt`, insert `f"{history_block}"` immediately after the `f"{game_rules}\n\n"` line (stage 1: after `f"{takeaway_block}"`). Use this script (it edits each function body in isolation and fails loudly if a target is missing):

```python
import re, sys
p = "src/endogenous/core/prompt_builders.py"
s = open(p).read()

def patch(func, signature_old, signature_new, body_old, body_new):
    global s
    start = s.index(f"def {func}(")
    end = s.find("\ndef ", start + 1)
    end = len(s) if end == -1 else end
    chunk = s[start:end]
    assert chunk.count(signature_old) == 1, (func, "signature")
    assert chunk.count(body_old) == 1, (func, "body")
    chunk = chunk.replace(signature_old, signature_new).replace(body_old, body_new)
    s = s[:start] + chunk + s[end:]

patch("build_stage1_prompt",
      "    takeaways: Optional[Dict[str, str]] = None,\n)",
      "    takeaways: Optional[Dict[str, str]] = None,\n    history_block: str = \"\",\n)",
      '        f"{takeaway_block}"\n',
      '        f"{takeaway_block}"\n        f"{history_block}"\n')
patch("build_stage2_prompt",
      "    prior_announcements: Optional[List[Dict[str, Any]]] = None,\n)",
      "    prior_announcements: Optional[List[Dict[str, Any]]] = None,\n    history_block: str = \"\",\n)",
      '        f"{game_rules}\\n\\n"\n        "You must make a strategic decision',
      '        f"{game_rules}\\n\\n"\n        f"{history_block}"\n        "You must make a strategic decision')
patch("build_stage3_prompt",
      "    supports_structured: bool = True\n)",
      "    supports_structured: bool = True,\n    history_block: str = \"\",\n)",
      '        f"{game_rules}\\n\\n"\n        "You must make a strategic decision',
      '        f"{game_rules}\\n\\n"\n        f"{history_block}"\n        "You must make a strategic decision')
patch("build_single_agent_reflection_prompt",
      "    supports_structured: bool = True,\n)",
      "    supports_structured: bool = True,\n    history_block: str = \"\",\n)",
      '        f"{game_rules}\\n\\n"\n        "You must make strategic decisions',
      '        f"{game_rules}\\n\\n"\n        f"{history_block}"\n        "You must make strategic decisions')
open(p, "w").write(s)
print("patched")
```

Also add `history_block` to each docstring's Args list in one line: `history_block: rendered history of earlier rounds ("" = none)`.

- [ ] **Step 4: Run to verify pass.** Run: `python -m unittest tests.test_history_prompts tests.test_history_block -v`. Expected: all OK.
- [ ] **Step 5: Commit** `git add -A src tests && git commit -m "prompt_builders: accept optional history_block in stage 1/2/3 and reflection prompts"`.

---

### Task 3: wire into the queued runner and CLI

**Files:** Modify `src/endogenous/core/trial_runner.py` (`run_all_trials_queued`), `experiments/run_endogenous.py`. Create `tests/test_history_integration.py`.

**Interfaces:**
- Consumes: `build_history_block`, `make_round_record` (Task 1), `history_block=` (Task 2).
- Produces: `run_all_trials_queued(..., use_history: bool = False)`; with it on, each agent entry gets `history_seen: str`; CLI `--history`; `metadata["history"]` in the saved JSON.

- [ ] **Step 1: Write the failing integration test** (`tests/test_history_integration.py`)

```python
import contextlib
import io
import unittest

from src.endogenous.core.trial_runner import run_all_trials_queued

PLANS = {"M": "CHEAP", "Q": "EXPENSIVE"}
PARAMS = {"expensive_joy": 10.0, "cheap_joy": 5.0, "expensive_cost": 8.0, "cheap_cost": 2.0}


class FakeClient:
    model = "meta-llama/fake"
    temperature = 1.0


class FakeQueued:
    """Answers every request with canned JSON and remembers the prompts."""

    def __init__(self):
        self.requests = {}

    def execute_all(self, reqs):
        out = {}
        for r in reqs:
            cid = r["custom_id"]
            self.requests[cid] = r["messages"]
            rnd, agent = cid.split("_")[0], cid.split("_")[-1]
            if "_s1_" in cid:
                out[cid] = {"intended_action": PLANS[agent], "reasoning": f"secret reasoning {agent}"}
            elif "_s2_" in cid:
                out[cid] = {"stated_action": "CHEAP", "message": f"{agent} promises CHEAP in {rnd}"}
            elif "_s3_" in cid:
                out[cid] = {"choice": "CHEAP", "reasoning": "r"}
            elif "_refl_" in cid:
                out[cid] = {"score": 3, "assessment": "fine"}
        return out


def run(use_history):
    fake = FakeQueued()
    with contextlib.redirect_stdout(io.StringIO()):
        rounds = run_all_trials_queued(
            game_type="diners", agent_names=["M", "Q"], game_params=PARAMS, llm_client=FakeClient(),
            queued_openrouter_client=fake, n_trials=1, n_rounds=2, round_robin=True,
            show_progress=False, use_history=use_history)
    return rounds, fake


def system_prompt(fake, cid):
    return fake.requests[cid][0]["content"]


class HistoryIntegrationTests(unittest.TestCase):
    def test_round_two_prompts_contain_round_one_history(self):
        rounds, fake = run(True)
        for stage in ("s1_M", "s2_M", "s3_M", "refl_M_about_Q"):
            with self.subTest(stage):
                prompt = system_prompt(fake, f"r1_t0_{stage}")
                self.assertIn("HISTORY OF PREVIOUS ROUNDS", prompt)
                self.assertIn("M promises CHEAP in r0", prompt)
                self.assertIn("Q promises CHEAP in r0", prompt)
                self.assertIn("Your private plan: CHEAP", prompt)

    def test_round_one_prompts_have_no_history(self):
        _, fake = run(True)
        for cid, messages in fake.requests.items():
            if cid.startswith("r0_"):
                self.assertNotIn("HISTORY", messages[0]["content"], cid)

    def test_nobody_sees_another_agents_plan_or_reasoning(self):
        _, fake = run(True)
        for cid, messages in fake.requests.items():
            text = messages[0]["content"]
            self.assertNotIn("secret reasoning", text, cid)
            if cid.endswith("_M") or "refl_M_" in cid:
                self.assertNotIn("Your private plan: EXPENSIVE", text, cid)

    def test_history_seen_is_logged_only_when_enabled(self):
        rounds, _ = run(True)
        self.assertEqual(rounds[0]["trials"][0]["agents"]["M"]["history_seen"], "")
        self.assertIn("Round 1:", rounds[1]["trials"][0]["agents"]["M"]["history_seen"])
        rounds_off, _ = run(False)
        self.assertNotIn("history_seen", rounds_off[1]["trials"][0]["agents"]["M"])

    def test_flag_off_leaves_prompts_without_history(self):
        _, fake = run(False)
        for cid, messages in fake.requests.items():
            self.assertNotIn("HISTORY", messages[0]["content"], cid)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure.** Run: `python -m unittest tests.test_history_integration -v`. Expected: `TypeError: ... unexpected keyword argument 'use_history'`.

- [ ] **Step 3: Implement `trial_runner.py`.**
  1. Import: `from src.endogenous.core.history import build_history_block, make_round_record`.
  2. Signature of `run_all_trials_queued`: add `use_history: bool = False,` after `queued_openrouter_client: Any = None,`; add a docstring line `use_history: render a per-agent history of earlier rounds into every prompt`.
  3. After `all_rounds: List[Dict[str, Any]] = []` add `history: Dict[int, List[Dict[str, Any]]] = {tid: [] for tid in trial_ids}`.
  4. Directly after `print(f"\n=== Round {round_idx + 1} / {n_rounds} ===")` add:
```python
        history_blocks = {
            (tid, agent): build_history_block(agent, history[tid]) if use_history else ""
            for tid in trial_ids for agent in agent_names
        }
```
  5. Add `history_block=history_blocks[(trial_id, agent_name)],` as the last argument of the five builder calls inside this function (stage 1; stage 2 simultaneous; stage 2 round-robin; stage 3; reflection). Each edit must match exactly one location (the end of the call's argument list); verify with `grep -c "history_block=history_blocks" src/endogenous/core/trial_runner.py` = 5.
  6. In the loop `for t in round_results:` that sets `t["round_id"]`, add after the `announcement_order` lines:
```python
            if use_history:
                for agent_name in agent_names:
                    t["agents"][agent_name]["history_seen"] = history_blocks[(t["trial_id"], agent_name)]
```
  7. Immediately after that loop (before the reflection section) add:
```python
        if use_history:
            for t in round_results:
                tid = t["trial_id"]
                history[tid].append(make_round_record(
                    round_idx,
                    plans={a: stage1_parsed[f"{tid}_{a}"].get("intended_action") for a in agent_names},
                    announcements={a: stage2_parsed[f"{tid}_{a}"] for a in agent_names},
                    outcomes=t["outcomes"],
                ))
```
  8. `experiments/run_endogenous.py`: add `parser.add_argument("--history", action="store_true", help="Give each agent a verbatim history of earlier rounds in its prompts (requires --use-queue).")`; after `args = parser.parse_args()` add `if args.history and not args.use_queue: parser.error("--history requires --use-queue")`; pass `use_history=args.history,` in the `run_all_trials_queued(...)` call; after `analysis = analyze_all_rounds(...)` add `analysis["metadata"]["history"] = args.history`.

- [ ] **Step 4: Run all tests.** Run: `python -m unittest discover -s tests -t . -v`. Expected: all OK (12 client tests + 6 + 3 + 5).
- [ ] **Step 5: CLI check.** Run: `python experiments/run_endogenous.py --history --game diners --agents 2 --trials 1 --rounds 1 --model x/y` with `OPENROUTER_API_KEY=dummy`. Expected: exit code 2, message `--history requires --use-queue`.
- [ ] **Step 6: Commit** `git add -A src experiments tests && git commit -m "Wire --history into the queued runner: per-agent history, history_seen logging"`.

---

### Task 4: live verification and docs

**Files:** Modify `SETUP_NOTES.md` on `sprint-3.3` (note: lives on a different branch than this feature).

- [ ] **Step 1: Live run.** From the worktree with the key exported (strip `\r`): `python experiments/run_endogenous.py --game diners --agents 2 --trials 1 --rounds 3 --model anthropic/claude-haiku-4.5 --use-queue --round-robin --history --run-suffix history --output-dir <scratch>`. Expected: 0 parse errors, 0 failed requests.
- [ ] **Step 2: Inspect.** In the JSON: `metadata.history == true`; round 1 `history_seen == ""`; rounds 2 and 3 `history_seen` contain the earlier verbatim messages; no other agent's plan appears. Read one round-3 stage-1 `reasoning` to see whether the agent refers to earlier rounds.
- [ ] **Step 3: Document.** Add a "History block" section to `SETUP_NOTES.md` on `sprint-3.3` (what was extended and why, flag, privacy rule, logging, branch, test results, and that results with and without `--history` are not comparable). Commit.
- [ ] **Step 4: Push the feature branch** only after user approval.
