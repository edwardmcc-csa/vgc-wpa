"""Version-drift check: fails loudly if the pinned Showdown submodule commit
or the resolved poke-env commit no longer matches docs/PINNED-VERSIONS.md.

pyproject.toml pins poke-env to a branch (@vgc-bench), not a commit, so a
fresh `pip install` can silently resolve to different code if that upstream
branch moves - with no change to this repo at all. The pokemon-showdown
submodule is pinned to a commit via git, but this still catches someone
bumping that pin (deliberately or not) without updating the recorded
version. Run in CI after submodules are checked out and `pip install .[dev]`
has run.
"""

import importlib.metadata
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PINS_FILE = REPO_ROOT / "docs" / "PINNED-VERSIONS.md"


def parse_pin(pins_text: str, name: str) -> str:
    """Extract the 40-char commit sha recorded for `name` in PINNED-VERSIONS.md."""
    match = re.search(
        rf"^- {re.escape(name)}: ([0-9a-f]{{40}})", pins_text, re.MULTILINE
    )
    if not match:
        raise ValueError(f"no pin recorded for {name!r} in {PINS_FILE}")
    return match.group(1)


def check_drift(name: str, expected: str, actual: str) -> str | None:
    """Return an error message if expected != actual, else None."""
    if expected == actual:
        return None
    return (
        f"{name} has drifted.\n"
        f"  expected (docs/PINNED-VERSIONS.md): {expected}\n"
        f"  actual:                             {actual}\n"
        f"  If this was an intentional upgrade, update docs/PINNED-VERSIONS.md "
        f"and commit that alongside it. Otherwise, something moved this pin "
        f"unexpectedly and it needs investigating before merging."
    )


def _actual_submodule_commit() -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT / "pokemon-showdown"), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _actual_poke_env_commit() -> str:
    dist = importlib.metadata.distribution("poke_env")
    direct_url_text = dist.read_text("direct_url.json")
    if direct_url_text is None:
        raise RuntimeError(
            "poke_env has no direct_url.json - was it installed from the pinned "
            "git ref, or from a different source (e.g. PyPI)?"
        )
    direct_url = json.loads(direct_url_text)
    commit = direct_url.get("vcs_info", {}).get("commit_id")
    if not commit:
        raise RuntimeError(
            f"could not find a resolved commit in poke_env's direct_url.json: "
            f"{direct_url}"
        )
    return commit


def main() -> int:
    pins_text = PINS_FILE.read_text(encoding="utf-8")
    checks = [
        ("pokemon-showdown submodule", _actual_submodule_commit),
        ("poke-env", _actual_poke_env_commit),
    ]
    failed = False
    for name, get_actual in checks:
        expected = parse_pin(pins_text, name)
        actual = get_actual()
        message = check_drift(name, expected, actual)
        if message is None:
            print(f"OK: {name} matches pinned commit {expected}")
        else:
            failed = True
            print(f"FAIL: {message}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
