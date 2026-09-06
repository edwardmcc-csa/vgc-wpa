"""Round-trip test for wpa.state's adapter to/from vgc-bench's trajectory format.

Their format -> ours -> theirs must come back unchanged. wpa/state.py does not
exist yet; this test is written first and is expected to fail on import.
"""

import numpy as np
from imitation.data.types import Trajectory

from wpa.state import WpaTrajectory


def _make_trajectory(num_states: int, obs_dim: int) -> Trajectory:
    rng = np.random.default_rng(0)
    obs = rng.random((num_states, obs_dim), dtype=np.float32)
    acts = rng.integers(0, 20, size=(num_states - 1, 2)).astype(np.int64)
    return Trajectory(obs=obs, acts=acts, infos=None, terminal=True)


def test_round_trip_preserves_observations_and_actions():
    original = _make_trajectory(num_states=6, obs_dim=6936)

    ours = WpaTrajectory.from_vgc_bench(original)
    back = ours.to_vgc_bench()

    assert np.array_equal(back.obs, original.obs)
    assert np.array_equal(back.acts, original.acts)
    assert back.terminal == original.terminal


def test_round_trip_does_not_alias_original_arrays():
    original = _make_trajectory(num_states=3, obs_dim=6936)
    ours = WpaTrajectory.from_vgc_bench(original)

    ours.observations[0, 0] = -999.0

    assert original.obs[0, 0] != -999.0


def test_round_trip_non_terminal_trajectory():
    original = _make_trajectory(num_states=4, obs_dim=6936)
    original = Trajectory(
        obs=original.obs, acts=original.acts, infos=None, terminal=False
    )

    back = WpaTrajectory.from_vgc_bench(original).to_vgc_bench()

    assert back.terminal is False
