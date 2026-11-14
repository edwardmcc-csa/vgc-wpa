# Pinned versions

Recorded: 2026-09-05T16:30:49Z

- fork commit: d79f9532947ac114dce1dda2456a590afcd375b2
- pokemon-showdown submodule: 913da3602a3aa1db79f9fdc5d5222eaf8d39569d
- pokemon-showdown-mc submodule: 7e743761cd13cdb361fc0f58eb5a866284894f5b
- poke-env: 379a04628e42b2a2c94790c0788204b652f7ae1b
- python: Python 3.14.3
- node: v26.7.0
- @smogon/calc: 0.12.0

**Two copies of Showdown's code (Week 14).** `pokemon-showdown` (the vgc-bench
fork, 20 Jun 2026) has the Reg M-A and M-B rules (mods `championsregma` and
`champions`) and stays for those two formats. `pokemon-showdown-mc` is
Showdown's own repository at 13 Nov 2026 (`Fix typo`), pinned by the PO's
decision of 14 Nov for Reg M-C (mod `champions`; it also has M-B as
`championsregmb`, and no longer has M-A). Both are checked below.

The damage calculator (`calc/`, Week 7) is pinned by `calc/package-lock.json`;
the same check fails if the version installed there is not the one above.

CI (.github/workflows/tests.yml, job "version-drift") fails the build if the
checked-out pokemon-showdown submodule commit or the resolved poke-env
commit no longer matches the two shas above. Both vgc-bench pins are branch
names, not fixed commits (`pokemon-showdown` tracks branch `vgc-bench` per
.gitmodules, `poke-env` tracks branch `vgc-bench` in pyproject.toml's git
dependency), so either can silently point at different code after a fresh
checkout/install with no change to this repo. If that happens legitimately,
update the two shas above in the same commit that acknowledges the move.
