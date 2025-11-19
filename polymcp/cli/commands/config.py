"""
Config Command - Manage PolyMCP configuration
"""

import click
import json
from pathlib import Path
from ..utils.config import Config


@click.group()
def config():
    """Manage PolyMCP configuration."""
    pass


@config.command('show')
@click.option('--global', 'is_global', is_flag=True, help='Show global config')
@click.pass_context
def show_config(ctx, is_global: bool):
    """
    Show current configuration.
    
    Examples:
      polymcp config show
      polymcp config show --global
    """
    config_dir = ctx.obj['config_dir'] if is_global else Path.cwd()
    cfg = Config(config_dir)
    
    click.echo(f"\n📋 Configuration ({config_dir}):\n")
    
    data = cfg.get_all()
    
    if not data:
        click.echo("No configuration set.")
        return
    
    click.echo(json.dumps(data, indent=2))


@config.command('set')
@click.argument('key')
@click.argument('value')
@click.option('--global', 'is_global', is_flag=True, help='Set in global config')
@click.pass_context
def set_config(ctx, key: str, value: str, is_global: bool):
    """
    Set a configuration value.
    
    Examples:
      polymcp config set llm.provider openai
      polymcp config set llm.model gpt-4
      polymcp config set agent.verbose true
    """
    config_dir = ctx.obj['config_dir'] if is_global else Path.cwd()
    cfg = Config(config_dir)
    
    # Try to parse value
    try:
        # Check if it's JSON
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        # Keep as string
        parsed_value = value
    
    cfg.set(key, parsed_value)
    click.echo(f"✅ Set {key} = {parsed_value}")


@config.command('get')
@click.argument('key')
@click.option('--global', 'is_global', is_flag=True, help='Get from global config')
@click.pass_context
def get_config(ctx, key: str, is_global: bool):
    """
    Get a configuration value.
    
    Examples:
      polymcp config get llm.provider
      polymcp config get agent.verbose
    """
    config_dir = ctx.obj['config_dir'] if is_global else Path.cwd()
    cfg = Config(config_dir)
    
    value = cfg.get(key)
    
    if value is None:
        click.echo(f"Key '{key}' not found", err=True)
    else:
        click.echo(value)


@config.command('delete')
@click.argument('key')
@click.option('--global', 'is_global', is_flag=True, help='Delete from global config')
@click.pass_context
def delete_config(ctx, key: str, is_global: bool):
    """
    Delete a configuration value.
    
    Examples:
      polymcp config delete llm.model
    """
    config_dir = ctx.obj['config_dir'] if is_global else Path.cwd()
    cfg = Config(config_dir)
    
    if cfg.delete(key):
        click.echo(f"✅ Deleted {key}")
    else:
        click.echo(f"Key '{key}' not found", err=True)


@config.command('init')
@click.option('--global', 'is_global', is_flag=True, help='Initialize global config')
@click.pass_context
def init_config(ctx, is_global: bool):
    """
    Initialize default configuration.
    
    Examples:
      polymcp config init
      polymcp config init --global
    """
    config_dir = ctx.obj['config_dir'] if is_global else Path.cwd()
    cfg = Config(config_dir)
    
    defaults = {
        "llm": {
            "provider": "ollama",
            "model": "llama3.2",
            "temperature": 0.7
        },
        "agent": {
            "type": "unified",
            "verbose": False,
            "max_steps": 10
        },
        "server": {
            "host": "0.0.0.0",
            "port": 8000
        }
    }
    
    for key, value in defaults.items():
        cfg.set(key, value)
    
    click.echo(f"✅ Initialized default configuration at {cfg.config_path}")
    click.echo("\nDefaults:")
    click.echo(json.dumps(defaults, indent=2))


@config.command('edit')
@click.option('--global', 'is_global', is_flag=True, help='Edit global config')
@click.pass_context
def edit_config(ctx, is_global: bool):
    """
    Open configuration file in editor.
    
    Examples:
      polymcp config edit
      polymcp config edit --global
    """
    import os
    
    config_dir = ctx.obj['config_dir'] if is_global else Path.cwd()
    cfg = Config(config_dir)
    
    editor = os.environ.get('EDITOR', 'nano')
    
    click.echo(f"Opening {cfg.config_path} with {editor}...")
    os.system(f"{editor} {cfg.config_path}")


@config.command('path')
@click.option('--global', 'is_global', is_flag=True, help='Show global config path')
@click.pass_context
def config_path(ctx, is_global: bool):
    """
    Show configuration file path.
    
    Examples:
      polymcp config path
      polymcp config path --global
    """
    config_dir = ctx.obj['config_dir'] if is_global else Path.cwd()
    cfg = Config(config_dir)
    
    click.echo(cfg.config_path)


@config.command('reset')
@click.option('--global', 'is_global', is_flag=True, help='Reset global config')
@click.option('--yes', is_flag=True, help='Skip confirmation')
@click.pass_context
def reset_config(ctx, is_global: bool, yes: bool):
    """
    Reset configuration to defaults.
    
    Examples:
      polymcp config reset
      polymcp config reset --global --yes
    """
    if not yes:
        if not click.confirm("Are you sure you want to reset configuration?"):
            click.echo("Cancelled.")
            return
    
    config_dir = ctx.obj['config_dir'] if is_global else Path.cwd()
    cfg = Config(config_dir)
    
    if cfg.config_path.exists():
        cfg.config_path.unlink()
        click.echo(f"✅ Reset configuration at {cfg.config_path}")
    else:
        click.echo("No configuration file to reset.")
