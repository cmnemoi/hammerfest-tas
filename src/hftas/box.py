"""Running hftas inside the hammerfest-tas distrobox, which holds Ruffle, libTAS and the build deps.

Called from the host, hftas re-runs itself in the box, so the same command works everywhere
(a shell, VS Code terminals, scripts). Without distrobox, or with HFTAS_NO_BOX=1, it runs in place.
"""

import os
import shutil
from pathlib import Path

BOX = "hammerfest-tas"
NO_BOX_ENV = "HFTAS_NO_BOX"


def should_enter_box(env: dict[str, str], distrobox: str | None) -> bool:
    in_container = bool(env.get("CONTAINER_ID"))  # set by distrobox (and toolbox) in every container
    return not in_container and distrobox is not None and env.get(NO_BOX_ENV) != "1"


def enter_box_if_needed(root: Path, argv: list[str]) -> None:
    """Replaces the current process with the same hftas command run inside the box, when on the host."""
    distrobox = shutil.which("distrobox")
    if not should_enter_box(dict(os.environ), distrobox):
        return
    # Login shell: puts mise on the PATH; mise then activates the venv holding hftas
    script = 'cd "$0" && exec mise exec -- hftas "$@"'
    os.execv(distrobox, [distrobox, "enter", BOX, "--", "bash", "-lc", script, str(root), *argv])
