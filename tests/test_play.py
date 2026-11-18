"""Playing the bot yourself (Week 16): the bot waits on the local Reg M-C server
and accepts a challenge from anyone, with a team from the pool; each game is
kept with the bot's own sheet, for the replay report."""

from __future__ import annotations

import random

import pytest

from wpa import play as P


def test_the_bots_team_is_the_one_asked_for_or_one_at_random():
    assert P.pick_team(40, 5, random.Random(0)) == 4  # team 5: the fifth
    got = {P.pick_team(40, None, random.Random(s)) for s in range(200)}
    assert got <= set(range(40)) and len(got) > 20
    with pytest.raises(SystemExit, match="1 to 40"):
        P.pick_team(40, 41, random.Random(0))


def test_each_game_is_kept_with_the_bots_own_sheet():
    from tests.test_bot import STREAM, TEAM

    log = P.kept_game(STREAM, "p1", TEAM)
    assert "|showteam|p1|" in log  # the bot's own sheet
    assert "|request|" not in log
    assert "|switch|p1a: Gholdengo|Gholdengo, L50|100/100" in log


def test_the_command_takes_a_name_and_a_team():
    a = P.parser().parse_args(["--team", "3", "--name", "My Bot"])
    assert (a.team, a.name, a.port) == (3, "My Bot", 8000)
    assert P.parser().parse_args([]).name == "WPA Bot"
