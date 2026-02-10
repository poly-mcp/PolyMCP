"""
skills.sh CLI passthrough for Python.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from typing import Iterable, Mapping, Optional


def _which_any(candidates: Iterable[str]) -> str | None:
    for name in candidates:
        found = shutil.which(name)
        if found:
            return found
    return None


def _resolve_skills_command(bin_override: Optional[str] = None) -> list[str]:
    env_bin = (
        bin_override
        or os.environ.get("POLYMCP_SKILLS_BIN")
        or os.environ.get("SKILLS_CLI")
    )
    if env_bin:
        return shlex.split(env_bin, posix=(sys.platform != "win32"))

    skills_bin = _which_any(["skills", "skills.cmd", "skills.exe"])
    if skills_bin:
        return [skills_bin]

    npx_bin = _which_any(["npx", "npx.cmd", "npx.exe"])
    if npx_bin:
        return [npx_bin, "-y", "skills"]

    return []


def run_skills_cli(
    args: Iterable[str],
    *,
    bin_override: Optional[str] = None,
    cwd: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
) -> int:
    """
    Run the skills.sh CLI and return the exit code.
    """
    cmd = _resolve_skills_command(bin_override)
    if not cmd:
        raise FileNotFoundError("skills CLI not found. Install Node.js or set POLYMCP_SKILLS_BIN.")
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    result = subprocess.run(
        [*cmd, *list(args)],
        cwd=cwd,
        env=merged_env,
        check=False,
    )
    return int(result.returncode or 0)
