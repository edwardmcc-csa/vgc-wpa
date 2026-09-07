"""Groups replay-corpus games into best-of-3 sets.

This is a grouping pass over data wpa.state.extract_bo3_context already
pulls out of each game's own log - not a re-scrape, and not a parallel
representation of the set fields already on wpa.state.BattleState.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from wpa.state import extract_bo3_context


@dataclass
class SetReconstructionResult:
    """sets: set_id -> {game_index: tag}. unassignable: tags whose set id
    and game index could not be extracted at all (no bestof banner, or
    malformed) - not the same as a set being incomplete in the corpus,
    which a fully-assignable game can still be part of."""

    sets: dict[str, dict[int, str]] = field(default_factory=dict)
    unassignable: list[str] = field(default_factory=list)


def reconstruct_sets(logs: dict[str, tuple[int, str]]) -> SetReconstructionResult:
    """Group every game in `logs` (tag -> (timestamp, log)) by its
    reconstructed best-of-3 set id."""
    result = SetReconstructionResult()
    for tag, (_timestamp, log) in logs.items():
        set_id, game_index, _score = extract_bo3_context(log)
        if set_id is None or game_index is None:
            result.unassignable.append(tag)
            continue
        games = result.sets.setdefault(set_id, {})
        if game_index in games:
            # Ambiguous: two games claiming the same index in the same
            # set. Treat both as unassignable rather than silently
            # picking one.
            result.unassignable.append(tag)
            result.unassignable.append(games.pop(game_index))
            if not games:
                del result.sets[set_id]
            continue
        games[game_index] = tag
    return result
