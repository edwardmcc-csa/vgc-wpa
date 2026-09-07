"""PokemonState carries which format gimmick (if any) a Pokemon has used.

Generic, not hardcoded to Terastallization: this format (M-A/M-B/M-C, see
docs/DEFINITIONS.md and the Week 2 Task 5 report) disables Tera entirely and
uses Mega Evolution instead - confirmed by a full-corpus scan finding zero
terastallize events, and by pokemon-showdown/data/mods/champions/scripts.ts's
canTerastallize unconditionally returning null. Which gimmick a format
allows is a fact about the format, not about our schema, so the field holds
a plain string ("mega", "tera", "dynamax") rather than a per-gimmick
boolean - a future regulation that reintroduces Tera needs no schema change.

wpa/state.py's PokemonState doesn't yet have a gimmick field; written first
and expected to fail.
"""

from wpa.state import BattleState, PokemonState, parse_battle_states


def test_pokemon_state_defaults_to_no_gimmick():
    p = PokemonState(species="pikachu", hp_fraction=1.0, fainted=False, active=True)
    assert p.gimmick is None


def test_pokemon_state_round_trips_gimmick_through_dict():
    original = BattleState(
        turn=3,
        our_pokemon=(PokemonState("charizard", 0.8, False, True, gimmick="mega"),),
        opp_pokemon=(PokemonState("pikachu", 1.0, False, False),),
        outcome=None,
    )

    restored = BattleState.from_dict(original.to_dict())

    assert restored == original
    assert restored.our_pokemon[0].gimmick == "mega"


def test_mega_evolution_detected_from_a_real_battle(sample_battles, reader_loop):
    tag, (_, log) = next(iter(sample_battles.items()))
    states = parse_battle_states(tag, log, "p1", reader_loop)

    gimmicks_seen = {
        mon.gimmick
        for state in states
        for mon in [*state.our_pokemon, *state.opp_pokemon]
        if mon.gimmick is not None
    }
    assert "mega" in gimmicks_seen
