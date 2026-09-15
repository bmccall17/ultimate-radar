"""The direction resolver, tested on invented quarters rather than on the footage.

Run them:

    python -m unittest discover -s tests -t .

`stdlib unittest`, not pytest: AGENTS rule 1 makes a dependency a licence row,
and this needs nothing pytest has. These are the only unit tests in the project
because this is the only module that is pure logic over a handful of facts - the
rest of the pipeline is graded by `python -m tools.gates` against real output,
which is the right instrument for it and the wrong one for "does a contradiction
between two humans actually come out as a contradiction".
"""

from __future__ import annotations

import unittest

from ur import direction as DIR


def obs(possession, quarter, team, d, teams=("sol", "chill")):
    return {"possession": possession, "quarter": quarter, "team": team,
            "direction": d, "teams": list(teams), "note": ""}


class Opposite(unittest.TestCase):
    def test_flips(self):
        self.assertEqual(DIR.opposite("+x"), "-x")
        self.assertEqual(DIR.opposite("-x"), "+x")

    def test_refuses_anything_else(self):
        with self.assertRaises(ValueError):
            DIR.opposite("left")


class ReadObservation(unittest.TestCase):
    CLIP = {"possession_id": "p0003", "quarter": 1, "offense": "sol",
            "defense": "chill", "teams": {"sol": {}, "chill": {}}}

    def test_nothing_observed(self):
        self.assertIsNone(DIR.read_observation(self.CLIP, {"events": []}))
        self.assertIsNone(DIR.read_observation(self.CLIP, {"observed": {}}))

    def test_object_form_names_its_team(self):
        o = DIR.read_observation(self.CLIP, {"observed": {
            "attacking_direction": {"team": "chill", "direction": "-x"}}})
        self.assertEqual((o["team"], o["direction"]), ("chill", "-x"))
        self.assertEqual(o["possession"], "p0003")
        self.assertEqual(o["quarter"], 1)

    def test_bare_string_means_the_offence(self):
        """The shape #5 wrote. It is about whoever `clip.json` says is attacking."""
        o = DIR.read_observation(self.CLIP, {"observed": {"attacking_direction": "+x"}})
        self.assertEqual((o["team"], o["direction"]), ("sol", "+x"))

    def test_refuses_a_direction_it_does_not_understand(self):
        with self.assertRaises(ValueError):
            DIR.read_observation(self.CLIP, {"observed": {"attacking_direction": "north"}})

    def test_refuses_a_team_not_in_the_game(self):
        with self.assertRaises(ValueError):
            DIR.read_observation(self.CLIP, {"observed": {
                "attacking_direction": {"team": "revolver", "direction": "+x"}}})

    def test_needs_a_quarter(self):
        clip = {**self.CLIP, "quarter": None}
        with self.assertRaises(ValueError):
            DIR.read_observation(clip, {"observed": {"attacking_direction": "+x"}})


class Resolve(unittest.TestCase):
    def test_nothing_in_means_nothing_out(self):
        table, conflicts = DIR.resolve([])
        self.assertEqual(table, {})
        self.assertEqual(conflicts, [])

    def test_one_confirmation_settles_the_quarter(self):
        table, conflicts = DIR.resolve([obs("p0003", 1, "sol", "+x")])
        self.assertEqual(conflicts, [])
        self.assertEqual(table[(1, "sol")]["direction"], "+x")
        self.assertEqual(table[(1, "sol")]["source"], "confirmed")
        self.assertEqual(table[(1, "chill")]["direction"], "-x")
        self.assertEqual(table[(1, "chill")]["source"], "derived")
        self.assertEqual(table[(1, "chill")]["from"], ["p0003"])

    def test_a_derived_direction_is_never_confirmed(self):
        """The brief's second trap: a solver's own output returning as a constraint."""
        table, _ = DIR.resolve([obs("p0003", 1, "sol", "+x")])
        derived = [v for v in table.values() if v["source"] == "derived"]
        self.assertTrue(derived)
        self.assertFalse(any(v["source"] == "confirmed" for v in derived))

    def test_two_possessions_agreeing_is_one_fact(self):
        table, conflicts = DIR.resolve([obs("p0003", 1, "sol", "+x"),
                                        obs("p0008", 1, "sol", "+x")])
        self.assertEqual(conflicts, [])
        self.assertEqual(table[(1, "sol")]["from"], ["p0003", "p0008"])

    def test_both_teams_confirmed_opposite_ways_is_fine(self):
        table, conflicts = DIR.resolve([obs("p0003", 1, "sol", "+x"),
                                        obs("p0009", 1, "chill", "-x")])
        self.assertEqual(conflicts, [])
        self.assertEqual(table[(1, "sol")]["source"], "confirmed")
        self.assertEqual(table[(1, "chill")]["source"], "confirmed")

    def test_one_team_told_two_ways_is_a_conflict_and_settles_nothing(self):
        table, conflicts = DIR.resolve([obs("p0003", 1, "sol", "+x"),
                                        obs("p0008", 1, "sol", "-x")])
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["quarter"], 1)
        self.assertNotIn((1, "sol"), table)
        self.assertNotIn((1, "chill"), table,
                         "a contradicted observation must not derive the opponent")

    def test_both_teams_attacking_the_same_end_is_a_conflict(self):
        """The one statement about the sport this whole check rests on."""
        table, conflicts = DIR.resolve([obs("p0003", 1, "sol", "+x"),
                                        obs("p0009", 1, "chill", "+x")])
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(table, {})

    def test_quarters_do_not_talk_to_each_other(self):
        """Teams swap ends between quarters, and nothing here knows when."""
        table, conflicts = DIR.resolve([obs("p0003", 1, "sol", "+x"),
                                        obs("p0004", 2, "sol", "+x")])
        self.assertEqual(conflicts, [])
        self.assertEqual(table[(1, "sol")]["direction"], "+x")
        self.assertEqual(table[(2, "sol")]["direction"], "+x")

    def test_a_conflict_in_one_quarter_leaves_the_others_standing(self):
        table, conflicts = DIR.resolve([obs("p0003", 1, "sol", "+x"),
                                        obs("p0009", 1, "chill", "+x"),
                                        obs("p0001", 4, "sol", "-x")])
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(table[(4, "sol")]["direction"], "-x")
        self.assertEqual(table[(4, "chill")]["direction"], "+x")


class Describe(unittest.TestCase):
    """One formatter, so no call site can quietly print a derivation as a fact."""

    def test_says_where_a_confirmation_came_from(self):
        table, _ = DIR.resolve([obs("p0003", 1, "sol", "+x")])
        self.assertEqual(DIR.describe(table[(1, "sol")]),
                         "sol +x (confirmed p0003)")

    def test_never_lets_a_derivation_read_as_a_confirmation(self):
        table, _ = DIR.resolve([obs("p0003", 1, "sol", "+x")])
        got = DIR.describe(table[(1, "chill")])
        self.assertEqual(got, "chill -x (derived from p0003)")
        self.assertNotIn("confirmed", got)


class ForPossession(unittest.TestCase):
    def test_unknown_quarter_is_not_a_guess(self):
        table, _ = DIR.resolve([obs("p0003", 1, "sol", "+x")])
        self.assertIsNone(DIR.for_possession(table, 2, "sol"))
        self.assertIsNone(DIR.for_possession(table, None, "sol"))

    def test_reads_the_derived_one_too(self):
        table, _ = DIR.resolve([obs("p0003", 1, "sol", "+x")])
        got = DIR.for_possession(table, 1, "chill")
        self.assertEqual(got["direction"], "-x")
        self.assertEqual(got["source"], "derived")


if __name__ == "__main__":
    unittest.main()
