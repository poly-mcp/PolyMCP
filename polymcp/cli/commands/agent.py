"""
Agent Command - Run and manage PolyMCP agents
"""

import click
import asyncio
import os
from pathlib import Path
from typing import Optional
from ..utils.config import Config
from ..utils.registry import ServerRegistry


@click.group()
def agent():
    """Run and manage PolyMCP agents."""
    pass


@agent.command('run')
@click.option('--type', 'agent_type', 
              type=click.Choice(['unified', 'codemode', 'basic', 'polyclaw']),
              default='unified',
              help='Agent type to use')
@click.option('--llm', type=click.Choice(['openai', 'anthropic', 'ollama']),
              help='LLM provider to use')
@click.option('--model', help='Model name')
@click.option('--servers', help='Comma-separated list of MCP server URLs')
@click.option('--verbose', is_flag=True, help='Enable verbose output')
@click.option('--query', help='Single query to execute (non-interactive)')
@click.option('--docker-image', default='python:3.11-slim', show_default=True,
              help='Docker image for polyclaw runtime')
@click.option('--docker-no-network', is_flag=True,
              help='Disable network inside polyclaw Docker runtime')
@click.option('--quiet', is_flag=True,
              help='Reduce polyclaw live transcript output')
@click.option('--intent', 'intent_mode',
              type=click.Choice(['auto', 'research', 'execution', 'mcp']),
              default='auto',
              show_default=True,
              help='Intent routing mode for polyclaw')
@click.option('--allow-bootstrap/--no-allow-bootstrap', default=True,
              show_default=True,
              help='Allow install/bootstrap commands for polyclaw')
@click.option('--strict-no-setup/--no-strict-no-setup', default=False,
              show_default=True,
              help='Block setup commands outside MCP orchestration intent')
@click.option('--confirm-delete/--no-confirm-delete', default=True,
              show_default=True,
              help='Ask confirmation before delete/remove commands in polyclaw')
@click.option('--max-iterations', default=24, show_default=True,
              help='Max loop iterations for polyclaw')
@click.option('--max-stagnant-steps', default=2, show_default=True,
              help='Stop early when polyclaw repeats same actions/results')
@click.pass_context
def run_agent(ctx, agent_type: str, llm: Optional[str], model: Optional[str], 
              servers: Optional[str], verbose: bool, query: Optional[str],
              docker_image: str, docker_no_network: bool, quiet: bool,
              intent_mode: str, allow_bootstrap: bool, strict_no_setup: bool,
              confirm_delete: bool,
              max_iterations: int, max_stagnant_steps: int):
    """
    Run an interactive PolyMCP agent.
    
    Examples:
      polymcp agent run
      polymcp agent run --type codemode
      polymcp agent run --type polyclaw --query "Create and test a local MCP server"
      polymcp agent run --type polyclaw --docker-image python:3.12-slim
      polymcp agent run --type polyclaw --intent research
      polymcp agent run --type polyclaw --strict-no-setup
      polymcp agent run --type polyclaw --no-confirm-delete
      polymcp agent run --type polyclaw --max-iterations 12
      polymcp agent run --type polyclaw --max-stagnant-steps 2
      polymcp agent run --type polyclaw --quiet
      polymcp agent run --llm openai --model gpt-4
      polymcp agent run --query "What is 2+2?"
      polymcp agent run --servers http://localhost:8000/mcp,http://localhost:8001/mcp
    """
    try:
        from polymcp.polyagent import UnifiedPolyAgent, CodeModeAgent, PolyAgent, PolyClawAgent
        from polymcp.polyagent.llm_providers import (
            OpenAIProvider, AnthropicProvider, OllamaProvider
        )
    except ImportError as e:
        click.echo(f" Error importing PolyMCP: {e}", err=True)
        click.echo("\nPlease install: pip install polymcp", err=True)
        return
    
    # Get servers
    if servers:
        server_list = [s.strip() for s in servers.split(',')]
    else:
        registry = ServerRegistry(Path.cwd())
        http_servers = registry.get_http_servers()
        server_list = list(http_servers.keys())
        
        if not server_list and agent_type != "polyclaw":
            click.echo(" No MCP servers configured", err=True)
            click.echo("\nAdd servers with: polymcp server add <url>", err=True)
            return
    
    # Create LLM provider
    try:
        llm_provider = _create_llm_provider(llm, model)
    except Exception as e:
        click.echo(f" Error creating LLM provider: {e}", err=True)
        return
    
    # Run async agent
    if asyncio.run(
        _run_agent_async(
            agent_type,
            llm_provider,
            server_list,
            verbose,
            query,
            docker_image,
            docker_no_network,
            quiet,
            intent_mode,
            allow_bootstrap,
            strict_no_setup,
            confirm_delete,
            max_iterations,
            max_stagnant_steps,
        )
    ):
        return
    else:
        click.echo(" Agent execution failed", err=True)


async def _run_agent_async(agent_type: str, llm_provider, server_list: list, 
                           verbose: bool, query: Optional[str],
                           docker_image: str, docker_no_network: bool, quiet: bool,
                           intent_mode: str, allow_bootstrap: bool, strict_no_setup: bool,
                           confirm_delete: bool,
                           max_iterations: int, max_stagnant_steps: int):
    """Run agent asynchronously."""
    from polymcp.polyagent import UnifiedPolyAgent, CodeModeAgent, PolyAgent, PolyClawAgent
    from polymcp.polyclaw import PolyClawConfig
    
    click.echo(f"\n Starting {agent_type.upper()} Agent")
    click.echo(f" MCP Servers: {len(server_list)}")
    if verbose:
        for s in server_list:
            click.echo(f"   • {s}")
    click.echo()
    
    # Create agent
    if agent_type == 'unified':
        agent = UnifiedPolyAgent(
            llm_provider=llm_provider,
            mcp_servers=server_list,
            verbose=verbose
        )
        
        async with agent:
            if query:
                # Single query mode
                response = await agent.run_async(query)
                click.echo(f"\n Agent: {response}\n")
                return True
            else:
                # Interactive mode
                return await _interactive_mode_async(agent)
    
    elif agent_type == 'codemode':
        agent = CodeModeAgent(
            llm_provider=llm_provider,
            mcp_servers=server_list,
            verbose=verbose
        )
        
        if query:
            response = agent.run(query)
            click.echo(f"\n Agent: {response}\n")
            return True
        else:
            return _interactive_mode_sync(agent)
    
    else:  # basic
        if agent_type == 'basic':
            agent = PolyAgent(
                llm_provider=llm_provider,
                mcp_servers=server_list,
                verbose=verbose
            )
        else:  # polyclaw
            polyclaw_config = PolyClawConfig(
                verbose=verbose,
                docker_image=docker_image,
                docker_enable_network=not docker_no_network,
                live_mode=not quiet,
                intent=intent_mode,
                allow_bootstrap=allow_bootstrap,
                strict_no_setup=strict_no_setup,
                confirm_delete_commands=confirm_delete,
                max_iterations=max(1, int(max_iterations)),
                max_stagnant_steps=max(1, int(max_stagnant_steps)),
            )
            agent = PolyClawAgent(
                llm_provider=llm_provider,
                mcp_servers=server_list,
                config=polyclaw_config,
                verbose=verbose,
            )

        if query:
            response = agent.run(query)
            click.echo(f"\n Agent: {response}\n")
            return True
        else:
            return _interactive_mode_sync(agent)


async def _interactive_mode_async(agent):
    """Interactive mode for async agents."""
    click.echo("Agent ready! Type 'quit' to exit.\n")
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                click.echo("\n Goodbye!")
                return True
            
            if not user_input:
                continue
            
            response = await agent.run_async(user_input)
            click.echo(f"\n Agent: {response}\n")
        
        except KeyboardInterrupt:
            click.echo("\n\n Goodbye!")
            return True
        except Exception as e:
            click.echo(f"\n Error: {e}\n")
            if not click.confirm("Continue?"):
                return False


def _interactive_mode_sync(agent):
    """Interactive mode for sync agents."""
    click.echo("Agent ready! Type 'quit' to exit.\n")
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                click.echo("\n Goodbye!")
                return True
            
            if not user_input:
                continue
            
            response = agent.run(user_input)
            click.echo(f"\n Agent: {response}\n")
        
        except KeyboardInterrupt:
            click.echo("\n\n Goodbye!")
            return True
        except Exception as e:
            click.echo(f"\n Error: {e}\n")
            if not click.confirm("Continue?"):
                return False


def _create_llm_provider(provider: Optional[str], model: Optional[str]):
    """Create LLM provider based on options."""
    from polymcp.polyagent.llm_providers import (
        OpenAIProvider, AnthropicProvider, OllamaProvider
    )
    
    # Auto-detect if not specified
    if not provider:
        if os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        elif os.getenv("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        else:
            provider = "ollama"
            click.echo("  No API keys found, using Ollama")
            click.echo("   Make sure Ollama is running: ollama serve\n")
    
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        return OpenAIProvider(
            api_key=api_key,
            model=model or "gpt-4"
        )
    
    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return AnthropicProvider(
            api_key=api_key,
            model=model or "claude-3-5-sonnet-20241022"
        )
    
    else:  # ollama
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return OllamaProvider(
            model=model or "llama3.2",
            base_url=base_url
        )


@agent.command('benchmark')
@click.option('--query', required=True, help='Query to benchmark')
@click.option('--iterations', default=3, help='Number of iterations')
@click.pass_context
def benchmark_agent(ctx, query: str, iterations: int):
    """
    Benchmark different agent types.
    
    Examples:
      polymcp agent benchmark --query "Add 2+2" --iterations 5
    """
    try:
        from polymcp.polyagent import UnifiedPolyAgent, CodeModeAgent, PolyAgent
        from polymcp.polyagent.llm_providers import OllamaProvider
        import time
    except ImportError as e:
        click.echo(f" Error: {e}", err=True)
        return
    
    registry = ServerRegistry(Path.cwd())
    servers = list(registry.get_http_servers().keys())
    
    if not servers:
        click.echo(" No servers configured", err=True)
        return
    
    llm = OllamaProvider(model="llama3.2")
    
    agent_types = [
        ('Basic', PolyAgent),
        ('CodeMode', CodeModeAgent),
        ('Unified', UnifiedPolyAgent)
    ]
    
    results = {}
    
    for agent_name, AgentClass in agent_types:
        click.echo(f"\n Testing {agent_name} Agent...")
        times = []
        
        for i in range(iterations):
            try:
                agent = AgentClass(
                    llm_provider=llm,
                    mcp_servers=servers,
                    verbose=False
                )
                
                start = time.time()
                
                if agent_name == 'Unified':
                    async def run():
                        async with agent:
                            return await agent.run_async(query)
                    asyncio.run(run())
                else:
                    agent.run(query)
                
                elapsed = time.time() - start
                times.append(elapsed)
                click.echo(f"   Iteration {i+1}: {elapsed:.2f}s")
            
            except Exception as e:
                click.echo(f"    Failed: {e}")
        
        if times:
            avg_time = sum(times) / len(times)
            results[agent_name] = avg_time
    
    # Show results
    if results:
        click.echo(f"\n{'='*50}")
        click.echo(" BENCHMARK RESULTS")
        click.echo(f"{'='*50}")
        click.echo(f"Query: {query}")
        click.echo(f"Iterations: {iterations}\n")
        
        sorted_results = sorted(results.items(), key=lambda x: x[1])
        
        for agent_name, avg_time in sorted_results:
            click.echo(f"  {agent_name:12} {avg_time:6.2f}s")
        
        fastest = sorted_results[0][0]
        click.echo(f"\n Fastest: {fastest}")
