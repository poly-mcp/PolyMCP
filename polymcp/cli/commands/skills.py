"""
Skills CLI Command - PRODUCTION IMPLEMENTATION
Complete CLI for managing MCP skills.

Production features:
- Generate skills from servers
- List available skills
- Show skill details
- Skill statistics
- Comprehensive error handling
"""

import click
import asyncio
import json
from pathlib import Path
from typing import Optional


@click.group()
def skills():
    """Manage MCP skills."""
    pass


@skills.command('generate')
@click.option('--servers', multiple=True, help='MCP server URLs')
@click.option('--registry', type=click.Path(exists=True), help='Server registry file')
@click.option('--output', default='./mcp_skills', help='Output directory')
@click.option('--timeout', default=10.0, help='Connection timeout')
@click.option('--verbose', is_flag=True, help='Verbose output')
@click.option('--no-examples', is_flag=True, help='Skip usage examples')
@click.pass_context
def generate_skills(
    ctx,
    servers: tuple,
    registry: Optional[str],
    output: str,
    timeout: float,
    verbose: bool,
    no_examples: bool
):
    """
    Generate skills from MCP servers.
    
    Examples:
      polymcp skills generate --servers http://localhost:8000/mcp
      polymcp skills generate --registry tool_registry.json
      polymcp skills generate --verbose
    """
    try:
        from polymcp.polyagent import MCPSkillGenerator
    except ImportError:
        click.echo("âŒ Error: MCPSkillGenerator not found", err=True)
        click.echo("Make sure skill_generator.py is installed", err=True)
        return
    
    # Collect server URLs
    server_list = list(servers)
    
    # Load from registry if provided
    if registry:
        try:
            with open(registry, 'r') as f:
                reg_data = json.load(f)
                reg_servers = reg_data.get('servers', [])
                server_list.extend(reg_servers)
                if verbose:
                    click.echo(f"ðŸ“„ Loaded {len(reg_servers)} servers from registry")
        except Exception as e:
            click.echo(f"âš ï¸  Failed to load registry: {e}", err=True)
    
    # Load from current project registry
    if not server_list:
        default_registry = Path.cwd() / "polymcp_registry.json"
        if default_registry.exists():
            try:
                with open(default_registry, 'r') as f:
                    reg_data = json.load(f)
                    reg_servers = reg_data.get('servers', {})
                    server_list.extend(reg_servers.keys())
                    if verbose:
                        click.echo(f"ðŸ“„ Loaded {len(server_list)} servers from project registry")
            except Exception as e:
                if verbose:
                    click.echo(f"âš ï¸  Failed to load project registry: {e}")
    
    if not server_list:
        click.echo("âŒ No MCP servers specified", err=True)
        click.echo("\nUse one of:", err=True)
        click.echo("  --servers http://localhost:8000/mcp", err=True)
        click.echo("  --registry tool_registry.json", err=True)
        click.echo("  Or create polymcp_registry.json in current directory", err=True)
        return
    
    # Create generator
    generator = MCPSkillGenerator(
        output_dir=output,
        verbose=verbose,
        include_examples=not no_examples
    )
    
    # Generate skills
    click.echo(f"\n{'='*60}")
    click.echo(f"🔎Generating Skills")
    click.echo(f"{'='*60}")
    click.echo(f"Servers: {len(server_list)}")
    click.echo(f"Output: {output}")
    click.echo(f"{'='*60}\n")
    
    try:
        stats = asyncio.run(
            generator.generate_from_servers(server_list, timeout=timeout)
        )
        
        # Display results
        click.echo(f"\n{'='*60}")
        click.echo(f"✅ GENERATION COMPLETE")
        click.echo(f"{'='*60}")
        click.echo(f"Tools discovered: {stats['total_tools']}")
        click.echo(f"Categories created: {len(stats['categories'])}")
        click.echo(f"Time: {stats['generation_time']:.2f}s")
        
        if stats.get('errors'):
            click.echo(f"\nErrors: {len(stats['errors'])}")
            for error in stats['errors'][:3]:
                click.echo(f"  • {error}")
        
        click.echo(f"\nOutput directory: {output}")
        click.echo(f"\nNext steps:")
        click.echo(f"  1. Review generated skills: polymcp skills list")
        click.echo(f"  2. Enable in agent: skills_enabled=True")
        click.echo(f"{'='*60}\n")
    
    except Exception as e:
        click.echo(f"\nGeneration failed: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()


@skills.command('list')
@click.option('--dir', 'skills_dir', default='./mcp_skills', help='Skills directory')
@click.option('--verbose', is_flag=True, help='Show details')
@click.pass_context
def list_skills(ctx, skills_dir: str, verbose: bool):
    """
    List available skills.
    
    Examples:
      polymcp skills list
      polymcp skills list --verbose
    """
    skills_path = Path(skills_dir)
    
    if not skills_path.exists():
        click.echo(f"Skills directory not found: {skills_dir}", err=True)
        click.echo(f"\nGenerate skills first: polymcp skills generate", err=True)
        return
    
    # Find skill files
    skill_files = list(skills_path.glob("*.md"))
    skill_files = [f for f in skill_files if not f.name.startswith("_")]
    
    if not skill_files:
        click.echo(f"No skills found in {skills_dir}", err=True)
        return
    
    click.echo(f"\n{'='*60}")
    click.echo(f"Available Skills")
    click.echo(f"{'='*60}")
    click.echo(f"Location: {skills_dir}")
    click.echo(f"Skills: {len(skill_files)}\n")
    
    # Load metadata if available
    metadata = {}
    meta_path = skills_path / "_metadata.json"
    if meta_path.exists():
        try:
            metadata = json.loads(meta_path.read_text())
        except:
            pass
    
    # List skills
    for skill_file in sorted(skill_files):
        category = skill_file.stem
        
        # Get tool count from metadata
        tool_count = metadata.get('stats', {}).get('categories', {}).get(category, 0)
        
        # Estimate tokens
        tokens = len(skill_file.read_text()) // 4
        
        click.echo(f"{category}")
        if verbose or tool_count:
            click.echo(f"     Tools: {tool_count}")
            click.echo(f"     Tokens: ~{tokens}")
            click.echo(f"     File: {skill_file.name}")
        click.echo()
    
    # Show totals
    if metadata:
        stats = metadata.get('stats', {})
        token_est = metadata.get('token_estimates', {})
        
        click.echo(f"{'='*60}")
        click.echo(f"Total tools: {stats.get('total_tools', 0)}")
        click.echo(f"Total tokens: ~{token_est.get('total', 0)}")
        click.echo(f"Avg per skill: ~{token_est.get('average_per_category', 0)}")
        click.echo(f"{'='*60}\n")


@skills.command('show')
@click.argument('category')
@click.option('--dir', 'skills_dir', default='./mcp_skills', help='Skills directory')
@click.pass_context
def show_skill(ctx, category: str, skills_dir: str):
    """
    Show details of a specific skill.
    
    Examples:
      polymcp skills show filesystem
      polymcp skills show api
    """
    skill_file = Path(skills_dir) / f"{category}.md"
    
    if not skill_file.exists():
        click.echo(f"âŒ Skill not found: {category}", err=True)
        click.echo(f"\nAvailable skills:", err=True)
        
        # List available
        skills_path = Path(skills_dir)
        if skills_path.exists():
            for f in sorted(skills_path.glob("*.md")):
                if not f.name.startswith("_"):
                    click.echo(f"  • {f.stem}", err=True)
        return
    
    # Display skill content
    content = skill_file.read_text()
    click.echo(content)


@skills.command('info')
@click.option('--dir', 'skills_dir', default='./mcp_skills', help='Skills directory')
@click.pass_context
def skills_info(ctx, skills_dir: str):
    """
    Show skills system information.
    
    Examples:
      polymcp skills info
    """
    skills_path = Path(skills_dir)
    
    if not skills_path.exists():
        click.echo(f"Skills directory not found: {skills_dir}", err=True)
        return
    
    # Load metadata
    meta_path = skills_path / "_metadata.json"
    if not meta_path.exists():
        click.echo(f"No metadata file found", err=True)
        return
    
    try:
        metadata = json.loads(meta_path.read_text())
    except Exception as e:
        click.echo(f"Failed to load metadata: {e}", err=True)
        return
    
    # Display info
    click.echo(f"\n{'='*60}")
    click.echo(f"Skills System Information")
    click.echo(f"{'='*60}\n")
    
    click.echo(f"Directory: {skills_dir}")
    click.echo(f"Generated: {metadata.get('generated_at', 'Unknown')}")
    click.echo(f"🔎Version: {metadata.get('version', 'Unknown')}\n")
    
    stats = metadata.get('stats', {})
    click.echo(f"Statistics:")
    click.echo(f"  Total tools: {stats.get('total_tools', 0)}")
    click.echo(f"  Total servers: {stats.get('total_servers', 0)}")
    click.echo(f"  Categories: {stats.get('total_categories', 0)}")
    click.echo(f"  Generation time: {stats.get('generation_time_seconds', 0):.2f}s\n")
    
    token_est = metadata.get('token_estimates', {})
    click.echo(f"Token Estimates:")
    click.echo(f"  Index: ~{token_est.get('index', 0)} tokens")
    click.echo(f"  Total: ~{token_est.get('total', 0)} tokens")
    click.echo(f"  Avg per category: ~{token_est.get('average_per_category', 0)} tokens\n")
    
    if stats.get('errors'):
        click.echo(f"Errors: {len(stats['errors'])}")
        for error in stats['errors'][:3]:
            click.echo(f"  • {error}")
        if len(stats['errors']) > 3:
            click.echo(f"  ... and {len(stats['errors']) - 3} more")
        click.echo()
    
    categories = stats.get('categories', {})
    if categories:
        click.echo(f"Categories:")
        for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:10]:
            click.echo(f"  • {cat}: {count} tools")
        if len(categories) > 10:
            click.echo(f"  ... and {len(categories) - 10} more")
        click.echo()
    
    click.echo(f"{'='*60}\n")


@skills.command('validate')
@click.option('--dir', 'skills_dir', default='./mcp_skills', help='Skills directory')
@click.pass_context
def validate_skills(ctx, skills_dir: str):
    """
    Validate skills directory structure.
    
    Examples:
      polymcp skills validate
    """
    skills_path = Path(skills_dir)
    
    issues = []
    warnings = []
    
    click.echo(f"\n🔎Validating skills directory: {skills_dir}\n")
    
    # Check directory exists
    if not skills_path.exists():
        click.echo(f"Directory not found: {skills_dir}", err=True)
        return
    
    # Check index file
    index_file = skills_path / "_index.md"
    if not index_file.exists():
        issues.append("Missing _index.md file")
    else:
        click.echo(f"✅ Index file found")
    
    # Check metadata
    meta_file = skills_path / "_metadata.json"
    if not meta_file.exists():
        warnings.append("Missing _metadata.json file")
    else:
        click.echo(f"✅ Metadata file found")
        
        # Validate JSON
        try:
            json.loads(meta_file.read_text())
            click.echo(f"✅ Metadata is valid JSON")
        except Exception as e:
            issues.append(f"Invalid metadata JSON: {e}")
    
    # Check skill files
    skill_files = list(skills_path.glob("*.md"))
    skill_files = [f for f in skill_files if not f.name.startswith("_")]
    
    if not skill_files:
        issues.append("No skill files found")
    else:
        click.echo(f"✅ Found {len(skill_files)} skill files")
    
    # Validate each skill file
    for skill_file in skill_files:
        content = skill_file.read_text()
        
        # Check for required sections
        if "## Overview" not in content:
            warnings.append(f"{skill_file.name}: Missing Overview section")
        if "## Available Tools" not in content:
            warnings.append(f"{skill_file.name}: Missing Available Tools section")
    
    # Display results
    click.echo(f"\n{'='*60}")
    if not issues and not warnings:
        click.echo(f"✅ Validation passed - no issues found")
    else:
        if issues:
            click.echo(f"Issues found: {len(issues)}")
            for issue in issues:
                click.echo(f"  • {issue}")
        if warnings:
            click.echo(f"\nWarnings: {len(warnings)}")
            for warning in warnings[:5]:
                click.echo(f"  • {warning}")
            if len(warnings) > 5:
                click.echo(f"  ... and {len(warnings) - 5} more")
    click.echo(f"{'='*60}\n")
