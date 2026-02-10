#!/usr/bin/env python3
"""
PolyMCP CLI - Main Entry Point
Complete command-line interface for PolyMCP management.
"""

import click
from pathlib import Path
import sys

from . import __version__

# Import commands - handle missing commands gracefully
try:
    from .commands import init, server, agent, test, config, skills
    has_commands = True
except ImportError:
    # If commands module doesn't exist, try importing directly
    try:
        from . import init, server, agent, test, config, skills
        has_commands = True
    except ImportError:
        has_commands = False

try:
    from .commands.inspector import inspector as inspector_cmd
    has_inspector = True
except ImportError:
    has_inspector = False



@click.group()
@click.version_option(version=__version__, prog_name="polymcp")
@click.pass_context
def cli(ctx):
    """
    PolyMCP CLI - Universal MCP Agent & Toolkit
    
    Manage MCP servers, agents, projects, and skills from the command line.
    
    \b
    Examples:
      polymcp init my-project          # Create new project
      polymcp server add http://...    # Add MCP server
      polymcp server list              # List configured servers
      polymcp agent run                # Run agent interactively
      polymcp skills                   # Run skills.sh CLI (npx skills)
      polymcp inspector                # Launch Inspector (NEW!)
      polymcp test server http://...   # Test MCP server
    """
    ctx.ensure_object(dict)
    ctx.obj['config_dir'] = Path.home() / '.polymcp'
    ctx.obj['config_dir'].mkdir(exist_ok=True)


# Register command groups
if has_commands:
    cli.add_command(init.init_cmd, name='init')
    cli.add_command(server.server, name='server')
    cli.add_command(agent.agent, name='agent')
    cli.add_command(test.test, name='test')
    cli.add_command(config.config, name='config')
    cli.add_command(skills.skills, name='skills')

# NEW: Register inspector command
if has_inspector:
    cli.add_command(inspector_cmd, name='inspector')

def main():
    """Entry point for CLI."""
    try:
        cli(obj={})
    except KeyboardInterrupt:
        click.echo("\n\nInterrupted by user", err=True)
        sys.exit(130)
    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
