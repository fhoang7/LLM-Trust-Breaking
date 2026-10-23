import contextlib
import io
import os
import unittest

# Building the judge request lazily imports src.config.settings, which refuses to import
# without an API key. No request is ever sent here, so a dummy key is enough.
os.environ.setdefault("OPENROUTER_API_KEY", "dummy-for-offline-tests")

from src.endogenous.core.swap import SwapConfig  # noqa: E402
from src.endogenous.core.trial_runner import run_all_trials_queued  # noqa: E402

NAMES = ["J", "M", "Q"]
PLANS = {"J": "CHEAP", "M": "CHEAP", "Q": "EXPENSIVE"}
PARAMS = {"expensive_joy": 10.0, "cheap_joy": 5.0, "expensive_cost": 8.0, "cheap_cost": 2.0}
BASE, OTHER = "meta-llama/fake-base", "meta-llama/fake-other"


class FakeClient:
    model = BASE
    temperature = 1.0


class FakeQueued:
    """Answers every request with canned JSON and remembers the full requests."""

    def __init__(self):
        self.requests = {}

    def execute_all(self, reqs):
        out = {}
        for r in reqs:
            cid = r["custom_id"]
            self.requests[cid] = r
            parts = cid.split("_")
            if cid.startswith("guess_"):
                draw = int(parts[3][1:])
                out[cid] = {"guess": "changed" if draw % 2 == 0 else "same", "confidence": 4, "reasoning": "x"}
            elif "_s1_" in cid:
                out[cid] = {"intended_action": PLANS[parts[-1]], "reasoning": "secret"}
            elif "_s2_" in cid:
                out[cid] = {"stated_action": "CHEAP", "message": f"{parts[-1]} promises CHEAP in {parts[0]}"}
            elif "_s3_" in cid:
                out[cid] = {"choice": "CHEAP", "reasoning": "r"}
            elif "_refl_" in cid:
                observer, target = cid.split("refl_")[1].split("_about_")
                out[cid] = {"score": 3, "assessment": f"{observer} thinks {target} fine"}
        return out


def run(swap, n_rounds=4, n_trials=1, use_history=True, agent_models=None):
    fake = FakeQueued()
    models = agent_models if agent_models is not None else {n: BASE for n in NAMES}
    with contextlib.redirect_stdout(io.StringIO()):
        rounds = run_all_trials_queued(
            game_type="diners", agent_names=NAMES, game_params=PARAMS, llm_client=FakeClient(),
            queued_openrouter_client=fake, n_trials=n_trials, n_rounds=n_rounds, round_robin=True,
            show_progress=False, agent_models=models, use_history=use_history, swap=swap)
    return rounds, fake, models


def sys_prompt(fake, cid):
    return fake.requests[cid]["messages"][0]["content"]


class SwapModelTests(unittest.TestCase):
    def test_model_changes_at_the_boundary_only_for_the_swapped_agent(self):
        _, fake, _ = run(SwapConfig(2, "Q", OTHER, "public"))
        for r in (0, 1):
            self.assertEqual(fake.requests[f"r{r}_t0_s1_Q"]["model"], BASE)
        for r in (2, 3):
            self.assertEqual(fake.requests[f"r{r}_t0_s1_Q"]["model"], OTHER)
            self.assertEqual(fake.requests[f"r{r}_t0_refl_Q_about_J"]["model"], OTHER)
        for r in range(4):
            self.assertEqual(fake.requests[f"r{r}_t0_s1_J"]["model"], BASE)

    def test_no_model_means_same_model_throughout(self):
        _, fake, _ = run(SwapConfig(2, "Q", None, "public"))
        self.assertEqual({r["model"] for cid, r in fake.requests.items() if cid.startswith("r")
                          and "s1_" in cid}, {BASE})

    def test_callers_agent_models_is_not_mutated(self):
        models = {n: BASE for n in NAMES}
        run(SwapConfig(2, "Q", OTHER, "public"), agent_models=models)
        self.assertEqual(set(models.values()), {BASE})

    def test_logging_records_model_used_and_swap_event(self):
        rounds, _, _ = run(SwapConfig(2, "Q", OTHER, "public"))
        self.assertEqual(rounds[1]["trials"][0]["agents"]["Q"]["model_used"], BASE)
        self.assertEqual(rounds[2]["trials"][0]["agents"]["Q"]["model_used"], OTHER)
        self.assertNotIn("swap_event", rounds[1]["trials"][0])
        self.assertEqual(rounds[2]["trials"][0]["swap_event"],
                         {"agent": "Q", "old_model": BASE, "new_model": OTHER, "inherit": "public",
                          "round_idx": 2})


class InheritanceTests(unittest.TestCase):
    def test_public_replacement_loses_private_plans_and_own_notes(self):
        _, fake, _ = run(SwapConfig(2, "Q", OTHER, "public"))
        before = sys_prompt(fake, "r1_t0_s1_Q")
        after = sys_prompt(fake, "r2_t0_s1_Q")
        self.assertIn("Your private plan: EXPENSIVE", before)
        self.assertIn("Q thinks J fine", before)
        self.assertIn("HISTORY OF PREVIOUS ROUNDS", after)
        self.assertIn("J promises CHEAP in r0", after)          # public history kept
        self.assertNotIn("Your private plan", after)
        self.assertNotIn("Q thinks J fine", after)              # own trust notes cleared

    def test_peers_keep_their_plans_and_their_notes_about_the_replaced_agent(self):
        _, fake, _ = run(SwapConfig(2, "Q", OTHER, "public"))
        j_after = sys_prompt(fake, "r2_t0_s1_J")
        self.assertIn("Your private plan: CHEAP", j_after)
        self.assertIn("J thinks Q fine", j_after)

    def test_full_inheritance_keeps_everything(self):
        _, fake, _ = run(SwapConfig(2, "Q", OTHER, "full"))
        after = sys_prompt(fake, "r2_t0_s1_Q")
        self.assertIn("Your private plan: EXPENSIVE", after)
        self.assertIn("Q thinks J fine", after)

    def test_history_seen_for_the_replacement_has_no_plan_lines(self):
        rounds, _, _ = run(SwapConfig(2, "Q", OTHER, "public"))
        self.assertNotIn("Your private plan", rounds[2]["trials"][0]["agents"]["Q"]["history_seen"])
        self.assertIn("Your private plan", rounds[2]["trials"][0]["agents"]["J"]["history_seen"])


class GuessStageTests(unittest.TestCase):
    def test_requests_cover_each_peer_and_draw_but_not_the_swapped_agent(self):
        _, fake, _ = run(SwapConfig(2, "Q", OTHER, "public", guess=True, guess_draws=3),
                         n_rounds=3, n_trials=2)
        guess_ids = sorted(c for c in fake.requests if c.startswith("guess_"))
        self.assertEqual(len(guess_ids), 2 * 2 * 3)
        self.assertFalse(any("_Q_" in c for c in guess_ids))

    def test_draws_use_distinct_seeds_and_peers_use_their_own_model(self):
        _, fake, _ = run(SwapConfig(2, "Q", OTHER, "public", guess=True, guess_draws=3), n_rounds=3)
        seeds = {fake.requests[f"guess_t0_J_d{k}"]["seed"] for k in range(3)}
        self.assertEqual(len(seeds), 3)
        self.assertEqual(fake.requests["guess_t0_J_d0"]["model"], BASE)

    def test_guess_prompt_contains_the_full_history_including_the_last_round(self):
        _, fake, _ = run(SwapConfig(2, "Q", OTHER, "public", guess=True, guess_draws=1), n_rounds=3)
        prompt = sys_prompt(fake, "guess_t0_J_d0")
        self.assertIn("Round 3:", prompt)
        self.assertIn("Q promises CHEAP in r2", prompt)

    def test_results_stored_on_the_last_round_trials(self):
        rounds, _, _ = run(SwapConfig(2, "Q", OTHER, "public", guess=True, guess_draws=3), n_rounds=3)
        g = rounds[-1]["trials"][0]["swap_guess"]
        self.assertEqual(g["target"], "Q")
        self.assertEqual(sorted(g["by_peer"]), ["J", "M"])
        self.assertEqual(len(g["by_peer"]["J"]["draws"]), 3)
        # draws 0 and 2 say changed (score 9), draw 1 says same (score 2): mean 20/3
        self.assertAlmostEqual(g["trial_changed_score"], 20 / 3)
        self.assertNotIn("swap_guess", rounds[0]["trials"][0])

    def test_no_guess_requests_without_the_flag(self):
        _, fake, _ = run(SwapConfig(2, "Q", OTHER, "public", guess=False), n_rounds=3)
        self.assertFalse(any(c.startswith("guess_") for c in fake.requests))


class DefaultsTests(unittest.TestCase):
    def test_swap_requires_history(self):
        with self.assertRaisesRegex(ValueError, "history"):
            run(SwapConfig(2, "Q", OTHER, "public"), use_history=False)

    def test_without_swap_nothing_new_is_logged_or_requested(self):
        rounds, fake, _ = run(None)
        agent = rounds[2]["trials"][0]["agents"]["Q"]
        self.assertNotIn("model_used", agent)
        self.assertNotIn("swap_event", rounds[2]["trials"][0])
        self.assertTrue(all(r["seed"] == 42 for r in fake.requests.values() if "seed" in r))


if __name__ == "__main__":
    unittest.main()
