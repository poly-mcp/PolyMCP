"""
Skills CLI Command - skills.sh passthrough

PolyMCP delegates skills management to the skills.sh CLI.
This command forwards all arguments to the external CLI.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from typing import Iterable, List

import click


def _which_any(candidates: Iterable[str]) -> str | None:
    for name in candidates:
        found = shutil.which(name)
        if found:
            return found
    return None


def _resolve_skills_command(bin_override: str | None) -> List[str]:
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


@click.command(
    context_settings={
        "ignore_unknown_options": True,
        "allow_extra_args": True,
    }
)
@click.option(
    "--bin",
    "bin_override",
    help="Override skills CLI binary. Also respects POLYMCP_SKILLS_BIN or SKILLS_CLI.",
)
@click.pass_context
def skills(ctx: click.Context, bin_override: str | None) -> None:
    """Run the skills.sh CLI via npx (or a provided binary)."""
    args = list(ctx.args)
    if not args:
        args = ["--help"]

    cmd = _resolve_skills_command(bin_override)
    if not cmd:
        click.echo("❌ skills CLI not found. Install Node.js or set POLYMCP_SKILLS_BIN.", err=True)
        raise SystemExit(1)

    try:
        result = subprocess.run(cmd + args, check=False)
        raise SystemExit(result.returncode)
    except FileNotFoundError:
        click.echo("❌ skills CLI not found. Install Node.js or set POLYMCP_SKILLS_BIN.", err=True)
        raise SystemExit(1)
