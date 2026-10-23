import unittest

from src.endogenous.core.swap import (
    SwapConfig, apply_swap, build_swap_config, build_swap_guess_prompt,
    changed_score, forced_choice, shows_private_plan, should_guess, summarize_guesses,
)

NAMES = ["J", "M", "Q"]
PARAMS = {"expensive_joy": 10.0, "cheap_joy": 5.0, "expensive_cost": 8.0, "cheap_cost": 2.0}


def cfg(**kw):
    base = dict(swap_at=3, agent="Q", model=None, inherit="public", guess=True, guess_draws=3,
                force_choice=None, game_type="diners",
                agent_names=NAMES, n_rounds=6, use_queue=True, use_history=True)
    base.update(kw)
    return build_swap_config(**base)


class BuildConfigTests(unittest.TestCase):
    def test_no_swap_when_swap_at_missing(self):
        self.assertIsNone(cfg(swap_at=None, agent=None, guess=False))

    def test_valid_config(self):
        c = cfg(model="deepseek/deepseek-v4-flash")
        self.assertEqual((c.swap_at, c.agent, c.model, c.inherit, c.guess, c.guess_draws),
                         (3, "Q", "deepseek/deepseek-v4-flash", "public", True, 3))
        self.assertIsNone(c.force_choice)

    def test_other_swap_options_without_swap_at_are_an_error(self):
        with self.assertRaisesRegex(ValueError, "--swap-at"):
            cfg(swap_at=None, model="x/y")

    def test_force_choice_options(self):
        self.assertEqual(cfg(force_choice="EXPENSIVE").force_choice, "EXPENSIVE")
        self.assertEqual(cfg(force_choice="cheap").force_choice, "CHEAP")      # normalised
        with self.assertRaisesRegex(ValueError, "CHEAP or EXPENSIVE"):
            cfg(force_choice="MAYBE")
        with self.assertRaisesRegex(ValueError, "diners"):
            cfg(force_choice="CHEAP", game_type="volunteer")
        with self.assertRaisesRegex(ValueError, "--swap-at"):
            cfg(swap_at=None, agent=None, guess=False, force_choice="CHEAP")

    def test_requires_queue_and_history(self):
        with self.assertRaisesRegex(ValueError, "--use-queue"):
            cfg(use_queue=False)
        with self.assertRaisesRegex(ValueError, "--history"):
            cfg(use_history=False)

    def test_swap_round_must_leave_rounds_on_both_sides(self):
        for bad in (0, 6, 7):
            with self.subTest(bad):
                with self.assertRaisesRegex(ValueError, "between 1 and 5"):
                    cfg(swap_at=bad)

    def test_agent_must_exist(self):
        with self.assertRaisesRegex(ValueError, "J, M, Q"):
            cfg(agent="Z")
        with self.assertRaisesRegex(ValueError, "--swap-agent"):
            cfg(agent=None)

    def test_inherit_and_draws_validated(self):
        with self.assertRaisesRegex(ValueError, "public"):
            cfg(inherit="half")
        with self.assertRaisesRegex(ValueError, "at least 1"):
            cfg(guess_draws=0)


class ApplySwapTests(unittest.TestCase):
    def setUp(self):
        self.takeaways = {
            t: {a: {o: {"score": 4, "assessment": f"{a}>{o}"} for o in NAMES if o != a} for a in NAMES}
            for t in (0, 1)
        }

    def test_model_replaced_and_event_returned(self):
        models = {n: "a/base" for n in NAMES}
        event = apply_swap(SwapConfig(3, "Q", "b/other", "full"), models, self.takeaways, [0, 1], NAMES)
        self.assertEqual(models, {"J": "a/base", "M": "a/base", "Q": "b/other"})
        self.assertEqual(event, {"agent": "Q", "old_model": "a/base", "new_model": "b/other", "inherit": "full"})

    def test_no_model_keeps_model(self):
        models = {n: "a/base" for n in NAMES}
        apply_swap(SwapConfig(3, "Q", None, "full"), models, self.takeaways, [0, 1], NAMES)
        self.assertEqual(set(models.values()), {"a/base"})

    def test_public_clears_only_the_replacements_own_notes(self):
        models = {n: "a/base" for n in NAMES}
        apply_swap(SwapConfig(3, "Q", None, "public"), models, self.takeaways, [0, 1], NAMES)
        for t in (0, 1):
            self.assertEqual(self.takeaways[t]["Q"], {"J": {}, "M": {}})
            self.assertEqual(self.takeaways[t]["J"]["Q"]["assessment"], "J>Q")
            self.assertEqual(self.takeaways[t]["M"]["J"]["assessment"], "M>J")

    def test_full_keeps_notes(self):
        models = {n: "a/base" for n in NAMES}
        apply_swap(SwapConfig(3, "Q", None, "full"), models, self.takeaways, [0, 1], NAMES)
        self.assertEqual(self.takeaways[0]["Q"]["J"]["assessment"], "Q>J")


class PrivatePlanVisibilityTests(unittest.TestCase):
    def test_only_the_public_replacement_after_the_swap_loses_plans(self):
        c = SwapConfig(3, "Q", None, "public")
        self.assertTrue(shows_private_plan(c, 2, "Q"))    # before the swap
        self.assertFalse(shows_private_plan(c, 3, "Q"))   # after the swap
        self.assertTrue(shows_private_plan(c, 3, "J"))    # peers unaffected
        self.assertTrue(shows_private_plan(SwapConfig(3, "Q", None, "full"), 4, "Q"))
        self.assertTrue(shows_private_plan(None, 4, "Q"))


class ForcedChoiceAndGuessTimingTests(unittest.TestCase):
    def test_forced_choice_only_for_the_swapped_agent_from_the_swap_round(self):
        c = SwapConfig(3, "Q", None, "public", force_choice="EXPENSIVE")
        self.assertIsNone(forced_choice(c, 2, "Q"))
        self.assertEqual(forced_choice(c, 3, "Q"), "EXPENSIVE")
        self.assertEqual(forced_choice(c, 5, "Q"), "EXPENSIVE")
        self.assertIsNone(forced_choice(c, 3, "J"))
        self.assertIsNone(forced_choice(SwapConfig(3, "Q"), 4, "Q"))
        self.assertIsNone(forced_choice(None, 4, "Q"))

    def test_guess_rounds_start_with_the_last_round_before_the_swap(self):
        c = SwapConfig(3, "Q", guess=True)          # swap before 0-indexed round 3
        self.assertEqual([r for r in range(6) if should_guess(c, r)], [2, 3, 4, 5])
        self.assertFalse(any(should_guess(SwapConfig(3, "Q", guess=False), r) for r in range(6)))
        self.assertFalse(should_guess(None, 4))


class ScoreTests(unittest.TestCase):
    def test_changed_score_mapping(self):
        self.assertEqual(changed_score("changed", 5), 10)
        self.assertEqual(changed_score("changed", 1), 6)
        self.assertEqual(changed_score("same", 1), 5)
        self.assertEqual(changed_score("same", 5), 1)
        self.assertEqual(changed_score(" Changed ", "4"), 9)

    def test_invalid_inputs_give_none(self):
        for g, c in (("maybe", 3), ("same", 0), ("same", 6), ("same", None), (None, 3), ("same", "x")):
            with self.subTest((g, c)):
                self.assertIsNone(changed_score(g, c))


class GuessPromptTests(unittest.TestCase):
    def test_prompt_is_neutral_and_carries_history(self):
        system, user, schema = build_swap_guess_prompt(
            "diners", "J", "Q", NAMES, PARAMS, history_block="HISTORY OF PREVIOUS ROUNDS\n\n")
        self.assertIn("You are Agent J", system)
        self.assertIn("HISTORY OF PREVIOUS ROUNDS", system)
        self.assertIn("Agent Q", user)
        self.assertIn("same", user)
        self.assertIn("changed", user)
        self.assertNotIn("replaced with", user.lower())
        self.assertEqual(schema["schema"]["required"], ["guess", "confidence", "reasoning"])
        self.assertEqual(schema["schema"]["properties"]["guess"]["enum"], ["same", "changed"])

    def test_unstructured_models_get_json_instructions(self):
        _, user, _ = build_swap_guess_prompt("diners", "J", "Q", NAMES, PARAMS, "", supports_structured=False)
        self.assertIn("ONLY a valid JSON object", user)


class SummarizeTests(unittest.TestCase):
    def draw(self, guess, conf):
        return {"guess": guess, "confidence": conf, "reason": "r",
                "changed_score": changed_score(guess, conf), "_parse_ok": changed_score(guess, conf) is not None}

    def test_averages_within_peer_then_across_peers(self):
        out = summarize_guesses("Q", {
            "J": [self.draw("changed", 5), self.draw("same", 5)],   # 10, 1 -> 5.5
            "M": [self.draw("same", 1)],                            # 5
        })
        self.assertAlmostEqual(out["by_peer"]["J"]["mean_changed_score"], 5.5)
        self.assertEqual(out["by_peer"]["J"]["changed_rate"], 0.5)
        self.assertAlmostEqual(out["trial_changed_score"], 5.25)
        self.assertEqual(out["target"], "Q")

    def test_unparsed_draws_are_excluded_and_all_failed_gives_none(self):
        bad = {"guess": None, "confidence": None, "reason": "", "changed_score": None, "_parse_ok": False}
        out = summarize_guesses("Q", {"J": [bad, self.draw("same", 3)], "M": [bad]})
        self.assertEqual(out["by_peer"]["J"]["n_valid"], 1)
        self.assertIsNone(out["by_peer"]["M"]["mean_changed_score"])
        self.assertAlmostEqual(out["trial_changed_score"], 3.0)
        self.assertIsNone(summarize_guesses("Q", {"J": [bad]})["trial_changed_score"])


if __name__ == "__main__":
    unittest.main()
