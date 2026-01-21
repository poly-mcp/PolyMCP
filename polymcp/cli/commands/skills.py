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
import shlex
import shutil
import sys
from pathlib import Path
from typing import Optional, Set


@click.group()
def skills():
    """Manage MCP skills."""
    pass


@skills.command('generate')
@click.option('--servers', multiple=True, help='MCP server URLs (HTTP) OR stdio commands if --stdio is enabled')
@click.option('--registry', type=click.Path(exists=True), help='Server registry file')
@click.option('--output', default='./mcp_skills', help='Output directory')
@click.option('--timeout', default=10.0, help='Connection timeout')
@click.option('--verbose', is_flag=True, help='Verbose output')
@click.option('--no-examples', is_flag=True, help='Skip usage examples')
# ✅ NEW: stdio gating
@click.option(
    '--stdio',
    is_flag=True,
    help='Enable stdio targets (non-HTTP) for skill generation (gated by allowlist).'
)
@click.option(
    '--allow-stdio-cmd',
    multiple=True,
    help='Allowlisted stdio executable names/paths (repeatable). Example: --allow-stdio-cmd npx'
)
@click.option(
    '--stdio-fallback',
    is_flag=True,
    help='Enable stdio fallback mapping (advanced; keep off unless you know you need it).'
)
@click.pass_context
def generate_skills(
    ctx,
    servers: tuple,
    registry: Optional[str],
    output: str,
    timeout: float,
    verbose: bool,
    no_examples: bool,
    stdio: bool,
    allow_stdio_cmd: tuple,
    stdio_fallback: bool,
):
    """
    Generate skills from MCP servers.

    Examples:
      # HTTP MCP:
      polymcp skills generate --servers http://localhost:8000/mcp --verbose

      # Stdio MCP (Playwright):
      polymcp skills generate --stdio --servers "npx @playwright/mcp@latest" --verbose

      # Stdio MCP (Filesystem):
      polymcp skills generate --stdio --servers "npx -y @modelcontextprotocol/server-filesystem C:\\path\\to\\root" --verbose

      # Stdio with explicit allowlist:
      polymcp skills generate --stdio --allow-stdio-cmd npx --servers "npx -y @modelcontextprotocol/server-filesystem C:\\path" --verbose
    """
    try:
        # MCPSkillGenerator always exists in your setup
        from polymcp.polyagent import MCPSkillGenerator
    except ImportError:
        click.echo("❌ Error: MCPSkillGenerator not found", err=True)
        click.echo("Make sure skill_generator.py is installed", err=True)
        return

    # Try to import StdioPolicy (location can vary depending on packaging)
    StdioPolicy = None
    try:
        from polymcp.polyagent import StdioPolicy as _StdioPolicy  # type: ignore
        StdioPolicy = _StdioPolicy
    except Exception:
        try:
            from polymcp.polyagent.skill_generator import StdioPolicy as _StdioPolicy  # type: ignore
            StdioPolicy = _StdioPolicy
        except Exception:
            StdioPolicy = None

    # Collect server targets
    server_list = list(servers)

    # Load from registry if provided
    if registry:
        try:
            with open(registry, 'r', encoding='utf-8') as f:
                reg_data = json.load(f)
                reg_servers = reg_data.get('servers', [])
                server_list.extend(reg_servers)
                if verbose:
                    click.echo(f"📄 Loaded {len(reg_servers)} servers from registry")
        except Exception as e:
            click.echo(f"⚠️  Failed to load registry: {e}", err=True)

    # Load from current project registry
    if not server_list:
        default_registry = Path.cwd() / "polymcp_registry.json"
        if default_registry.exists():
            try:
                with open(default_registry, 'r', encoding='utf-8') as f:
                    reg_data = json.load(f)
                    reg_servers = reg_data.get('servers', {})
                    server_list.extend(reg_servers.keys())
                    if verbose:
                        click.echo(f"📄 Loaded {len(server_list)} servers from project registry")
            except Exception as e:
                if verbose:
                    click.echo(f"⚠️  Failed to load project registry: {e}")

    if not server_list:
        click.echo("❌ No MCP servers specified", err=True)
        click.echo("\nUse one of:", err=True)
        click.echo("  --servers http://localhost:8000/mcp", err=True)
        click.echo("  --registry tool_registry.json", err=True)
        click.echo("  Or create polymcp_registry.json in current directory", err=True)
        return

    # ----------------------------
    # ✅ Build stdio policy (if enabled)
    # ----------------------------
    stdio_policy_obj = None
    if stdio:
        if StdioPolicy is None:
            click.echo("❌ StdioPolicy not importable. Update polymcp.polyagent exports or module path.", err=True)
            return

        allowed: Set[str] = set()

        # 1) User-provided allowlist
        for item in allow_stdio_cmd:
            if item:
                allowed.add(str(item))

        # 2) If not provided, auto-allow only the commands actually referenced in --servers
        #    (keeps it secure-by-default while removing the annoying block)
        if not allowed:
            for target in server_list:
                # Only consider non-http targets as potential commands
                t = str(target).strip()
                if t.startswith("http://") or t.startswith("https://"):
                    continue
                try:
                    parts = shlex.split(t, posix=(sys.platform != "win32"))
                except Exception:
                    parts = t.split()

                if not parts:
                    continue

                cmd = parts[0]
                allowed.add(cmd)

                # Add resolved absolute paths too (Windows-friendly)
                resolved = shutil.which(cmd)
                if resolved:
                    allowed.add(str(Path(resolved).resolve()))

                if sys.platform == "win32":
                    # Common Windows variants
                    for variant in (cmd + ".cmd", cmd + ".exe"):
                        resolved_v = shutil.which(variant)
                        if resolved_v:
                            allowed.add(str(Path(resolved_v).resolve()))

        if not allowed:
            click.echo("❌ --stdio enabled but no allowed stdio commands could be determined.", err=True)
            click.echo("Provide at least one: --allow-stdio-cmd npx", err=True)
            return

        stdio_policy_obj = StdioPolicy(
            enable_stdio_fallback=bool(stdio_fallback),
            enable_stdio_commands=True,
            allowed_commands=allowed,
        )

        if verbose:
            click.echo("🛡️  Stdio enabled with allowlist:")
            for a in sorted(allowed):
                click.echo(f"  - {a}")

    # Create generator (unchanged defaults; just inject stdio_policy if requested)
    generator_kwargs = dict(
        output_dir=output,
        verbose=verbose,
        include_examples=not no_examples
    )
    if stdio_policy_obj is not None:
        generator_kwargs["stdio_policy"] = stdio_policy_obj

    generator = MCPSkillGenerator(**generator_kwargs)

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
        click.echo(f"❌ Skill not found: {category}", err=True)
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
            click.echo(f"  . and {len(stats['errors']) - 3} more")
        click.echo()

    categories = stats.get('categories', {})
    if categories:
        click.echo(f"Categories:")
        for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:10]:
            click.echo(f"  • {cat}: {count} tools")
        if len(categories) > 10:
            click.echo(f"  . and {len(categories) - 10} more")
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

    # Check for index file
    index_candidates = [skills_path / "INDEX.md", skills_path / "_index.md"]
    if not any(p.exists() for p in index_candidates):
        warnings.append("Missing INDEX.md (or _index.md)")

    # Check for metadata file
    meta_candidates = [skills_path / "metadata.json", skills_path / "_metadata.json"]
    if not any(p.exists() for p in meta_candidates):
        warnings.append("Missing metadata.json (or _metadata.json)")

    # Check for skill files
    skill_files = [f for f in skills_path.glob("*.md") if not f.name.startswith("_") and f.name.upper() != "INDEX.MD"]
    if not skill_files:
        issues.append("No skill category files found (*.md)")

    # Report
    if issues:
        click.echo("❌ Issues found:")
        for i in issues:
            click.echo(f"  • {i}")
        click.echo()

    if warnings:
        click.echo("⚠️  Warnings:")
        for w in warnings:
            click.echo(f"  • {w}")
        click.echo()

    if not issues:
        click.echo("✅ Skills directory looks valid.\n")
