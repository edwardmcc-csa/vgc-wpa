# Pinned versions

Recorded: 2026-09-05T16:30:49Z

- fork commit: d79f9532947ac114dce1dda2456a590afcd375b2
- pokemon-showdown submodule: 913da3602a3aa1db79f9fdc5d5222eaf8d39569d
- poke-env: 379a04628e42b2a2c94790c0788204b652f7ae1b
- python: Python 3.14.3
- node: v26.7.0

CI (.github/workflows/tests.yml, job "version-drift") fails the build if the
checked-out pokemon-showdown submodule commit or the resolved poke-env
commit no longer matches the two shas above. Both vgc-bench pins are branch
names, not fixed commits (`pokemon-showdown` tracks branch `vgc-bench` per
.gitmodules, `poke-env` tracks branch `vgc-bench` in pyproject.toml's git
dependency), so either can silently point at different code after a fresh
checkout/install with no change to this repo. If that happens legitimately,
update the two shas above in the same commit that acknowledges the move.
