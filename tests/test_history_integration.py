import contextlib
import io
import os
import unittest

# Building the judge request lazily imports src.config.settings, which refuses to import
# without an API key. No request is ever sent here, so a dummy key is enough.
os.environ.setdefault("OPENROUTER_API_KEY", "dummy-for-offline-tests")

from src.endogenous.core.trial_runner import run_all_trials_queued  # noqa: E402

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
        _, fake = run(True)
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
            # The viewing agent is the one after "refl_" for reflections, else the last token.
            viewer = cid.split("refl_")[1].split("_")[0] if "_refl_" in cid else cid.split("_")[-1]
            other_plan = PLANS["Q" if viewer == "M" else "M"]
            if other_plan != PLANS[viewer]:
                self.assertNotIn(f"Your private plan: {other_plan}", text, cid)

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
