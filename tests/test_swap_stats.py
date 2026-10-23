import unittest

from src.endogenous.analysis.swap_stats import (
    bootstrap_ci, diff_ci, permutation_pvalue, trial_metrics,
)


def agent(stated, choice, takeaways=None):
    out = {"stage2": {"stated_action": stated}, "stage3": {"choice": choice}}
    if takeaways is not None:
        out["reflection"] = {"takeaways": {t: {"score": s, "assessment": "a"} for t, s in takeaways.items()}}
    return out


def fake_rounds():
    """One trial, 4 rounds, agents J M Q, swap of Q after round 2.

    Pre (rounds 0-1): J and M trust Q at 5, always keep promises and choose CHEAP.
    Post (rounds 2-3): J and M trust Q at 3; J starts announcing CHEAP but choosing EXPENSIVE.
    """
    rounds = []
    for r in range(4):
        post = r >= 2
        trust_q = 3 if post else 5
        j = agent("CHEAP", "EXPENSIVE" if post else "CHEAP", {"Q": trust_q, "M": 5})
        m = agent("CHEAP", "CHEAP", {"Q": trust_q, "J": 5})
        q = agent("CHEAP", "CHEAP", {"J": 1, "M": 1})   # Q's own opinions must be ignored
        trial = {"trial_id": 0, "agents": {"J": j, "M": m, "Q": q}}
        rounds.append({"round_id": r, "trials": [trial]})
    rounds[-1]["trials"][0]["swap_guess"] = {"trial_changed_score": 7.5}
    return rounds


class TrialMetricsTests(unittest.TestCase):
    def test_metrics_for_a_known_game(self):
        m = trial_metrics(fake_rounds(), swap_agent="Q", swap_at=2)[0]
        self.assertEqual(m["guess_score"], 7.5)
        self.assertAlmostEqual(m["trust_delta"], 3 - 5)               # peers' trust in Q: 5 -> 3
        # incumbents J,M: CHEAP rate pre 1.0; post J:0 M:1 -> 0.5
        self.assertAlmostEqual(m["coop_delta"], 0.5 - 1.0)
        # announce-vs-choose gap pre 0.0; post J differs, M does not -> 0.5
        self.assertAlmostEqual(m["gap_delta"], 0.5 - 0.0)

    def test_missing_pieces_give_none(self):
        rounds = fake_rounds()
        del rounds[-1]["trials"][0]["swap_guess"]
        for r in rounds:
            for a in r["trials"][0]["agents"].values():
                a.pop("reflection", None)
        m = trial_metrics(rounds, "Q", 2)[0]
        self.assertIsNone(m["guess_score"])
        self.assertIsNone(m["trust_delta"])
        self.assertIsNotNone(m["coop_delta"])


class BootstrapTests(unittest.TestCase):
    def test_mean_and_interval_bracket_the_data(self):
        out = bootstrap_ci([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], n_boot=2000, seed=1)
        self.assertAlmostEqual(out["mean"], 5.5)
        self.assertLess(out["lo"], 5.5)
        self.assertGreater(out["hi"], 5.5)
        self.assertGreaterEqual(out["lo"], 1)
        self.assertLessEqual(out["hi"], 10)
        self.assertEqual(out["n"], 10)

    def test_same_seed_same_answer(self):
        v = [1.0, 4.0, 2.0, 8.0, 5.0, 7.0]
        self.assertEqual(bootstrap_ci(v, n_boot=500, seed=3), bootstrap_ci(v, n_boot=500, seed=3))

    def test_none_values_dropped_and_too_few_gives_none(self):
        self.assertEqual(bootstrap_ci([1, None, 3], n_boot=200, seed=0)["n"], 2)
        self.assertIsNone(bootstrap_ci([1.0], n_boot=200))
        self.assertIsNone(bootstrap_ci([None, None], n_boot=200))

    def test_constant_data_has_a_zero_width_interval(self):
        out = bootstrap_ci([2.0] * 6, n_boot=300, seed=0)
        self.assertEqual((out["lo"], out["hi"]), (2.0, 2.0))


class DiffTests(unittest.TestCase):
    def test_separated_groups_exclude_zero(self):
        a = [8, 9, 9, 10, 8, 9, 10, 9, 8, 9]
        b = [2, 3, 2, 1, 3, 2, 2, 3, 1, 2]
        out = diff_ci(a, b, n_boot=2000, seed=1)
        self.assertGreater(out["lo"], 0)
        self.assertAlmostEqual(out["diff"], sum(a) / 10 - sum(b) / 10)

    def test_identical_groups_include_zero(self):
        a = [3, 5, 4, 6, 5, 4, 3, 5, 6, 4]
        out = diff_ci(a, list(reversed(a)), n_boot=2000, seed=1)
        self.assertLessEqual(out["lo"], 0)
        self.assertGreaterEqual(out["hi"], 0)

    def test_too_few_gives_none(self):
        self.assertIsNone(diff_ci([1.0], [1.0, 2.0]))


class PermutationTests(unittest.TestCase):
    def test_separated_groups_give_small_p(self):
        a = [8, 9, 9, 10, 8, 9, 10, 9, 8, 9]
        b = [2, 3, 2, 1, 3, 2, 2, 3, 1, 2]
        self.assertLess(permutation_pvalue(a, b, n_perm=2000, seed=1), 0.01)

    def test_identical_groups_give_large_p(self):
        a = [3, 5, 4, 6, 5, 4, 3, 5, 6, 4]
        self.assertGreater(permutation_pvalue(a, list(reversed(a)), n_perm=2000, seed=1), 0.5)

    def test_p_is_never_zero(self):
        self.assertGreater(permutation_pvalue([10] * 5, [0] * 5, n_perm=200, seed=0), 0)

    def test_too_few_gives_none(self):
        self.assertIsNone(permutation_pvalue([1.0], [2.0, 3.0]))


if __name__ == "__main__":
    unittest.main()
