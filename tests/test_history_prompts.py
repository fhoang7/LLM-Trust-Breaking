import unittest

from src.endogenous.core import prompt_builders as pb

BLOCK = "HISTORY OF PREVIOUS ROUNDS (what you have observed so far):\nRound 1:\n  marker-line\n\n"
NAMES = ["M", "Q"]
PARAMS = {"expensive_joy": 10.0, "cheap_joy": 5.0, "expensive_cost": 8.0, "cheap_cost": 2.0}
S1 = {"intended_action": "CHEAP", "reasoning": "r"}
S2 = {"M": {"stated_action": "CHEAP", "message": "hi"}, "Q": {"stated_action": "CHEAP", "message": "yo"}}
OUT = {"choices": {"M": "CHEAP", "Q": "CHEAP"}, "payoffs": {"M": 3.0, "Q": 3.0}, "description": "d"}


def calls():
    """name -> callable(**kw) returning (system, user, schema)."""
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

    def test_block_appears_in_system_prompt_after_game_rules(self):
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
