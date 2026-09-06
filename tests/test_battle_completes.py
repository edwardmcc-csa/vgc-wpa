"""One VGC doubles battle between two baseline poke-env agents, played to
completion against a local Showdown server.

wpa/battle.py does not exist yet; written first and expected to fail.
"""

import socket

import pytest

from wpa.battle import SHOWDOWN_PORT, play_one_battle


def _server_available() -> bool:
    try:
        with socket.create_connection(("localhost", SHOWDOWN_PORT), timeout=1):
            return True
    except OSError:
        return False


requires_server = pytest.mark.skipif(
    not _server_available(),
    reason=f"no Pokemon Showdown server running on port {SHOWDOWN_PORT}",
)


@requires_server
def test_battle_completes_with_exactly_one_winner():
    result = play_one_battle()

    assert result.finished
    assert result.winner is not None
    assert result.winner in (result.p1_username, result.p2_username)
