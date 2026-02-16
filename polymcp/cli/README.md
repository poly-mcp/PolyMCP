<p align="center">
  <img src="polymcp-cli.png" alt="PolymCP CLI Logo" width="500"/>
</p>

<p align="center">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <img src="https://img.shields.io/badge/python-%3E%3D3.8-blue" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/CLI-production-ready-green" alt="CLI status">
</p>

> Command-line interface for creating projects, registering MCP servers, running agents, and validating integrations.

Version: 1.3.6

## What This CLI Does

The `polymcp` command gives a full operator workflow:
- bootstrap new projects
- manage HTTP and stdio MCP server registry
- run interactive agents
- test servers, tools, auth, and stdio endpoints
- manage skills via skills.sh
- launch Inspector

## Install

```bash
pip install polymcp
```

## Quick Workflow

```bash
# 1) Create a server project
polymcp init my-project --type http-server --with-examples

# 2) Run server
cd my-project
python server.py

# 3) Validate integration
polymcp test server http://localhost:8000/mcp
polymcp test tool http://localhost:8000/mcp greet --params '{"name":"World"}'

# 4) Register and use with agent
polymcp server add http://localhost:8000/mcp --name local
polymcp agent run
```

## Command Reference

### `polymcp init`

```bash
polymcp init my-project
polymcp init my-project --type stdio-server
polymcp init my-project --type agent --with-examples
polymcp init my-project --with-auth
```

Supported types:
- `basic`
- `http-server`
- `stdio-server`
- `wasm-server`
- `agent`

### `polymcp server`

```bash
polymcp server add http://localhost:8000/mcp --name local
polymcp server add stdio://playwright --type stdio --command npx --args @playwright/mcp@latest
polymcp server list
polymcp server info http://localhost:8000/mcp
polymcp server remove http://localhost:8000/mcp
```

### `polymcp agent`

```bash
polymcp agent run
polymcp agent run --type unified
polymcp agent run --type codemode
polymcp agent run --type polyclaw
polymcp agent run --type polyclaw --docker-image python:3.12-slim
polymcp agent run --type polyclaw --docker-no-network
polymcp agent run --type polyclaw --quiet
polymcp agent run --type polyclaw --intent research
polymcp agent run --type polyclaw --intent mcp
polymcp agent run --type polyclaw --strict-no-setup
polymcp agent run --type polyclaw --no-allow-bootstrap
polymcp agent run --type polyclaw --no-confirm-delete
polymcp agent run --type polyclaw --max-iterations 12
polymcp agent run --type polyclaw --max-stagnant-steps 2
polymcp agent run --query "Summarize latest server output"
polymcp agent benchmark --query "Add 2 and 2" --iterations 5
```

`🦞 polyclaw` is the autonomous OpenClaw-style agent for end-to-end execution.
It executes shell steps inside Docker and mounts the current project at `/workspace`.
It can create/configure/test MCP servers with `polymcp` CLI when useful for the task.
It shows a live transcript (`THINK`, `SAY`, `ACTION`, `OUTPUT`) by default; use `--quiet` to reduce output.
It supports intent routing (`--intent auto|research|execution|mcp`); in `auto` it decides the intent by itself.
By default it runs in autonomous mode (bootstrap/setup allowed if useful).
Use `--strict-no-setup` and/or `--no-allow-bootstrap` for a stricter constrained mode.
Delete/remove commands require interactive confirmation by default (`--confirm-delete`).
Confirmation choices: `y` yes once, `n` no and block next delete commands in this run, `a` always yes, `x` always no.
In strict research mode without connected tools/servers, it uses built-in web retrieval (no shell) before fallback.
It stops early when it detects repeated identical actions/results (`--max-stagnant-steps`).
Python example: `examples/polyclaw_example.py`.
Advanced workflow example: `examples/polyclaw_mcp_workflow_example.py`.

### `polymcp test`

```bash
polymcp test server http://localhost:8000/mcp
polymcp test tool http://localhost:8000/mcp add --params '{"a":2,"b":3}'
polymcp test auth http://localhost:8000
polymcp test stdio npx @playwright/mcp@latest
polymcp test all
```

### `polymcp skills`

PolyMCP delegates skills management to the skills.sh CLI.

```bash
# Show skills CLI help
polymcp skills --help

# Add skills in current project (./.agents/skills)
polymcp skills add vercel-labs/agent-skills

# Add skills globally (~/.agents/skills)
polymcp skills add vercel-labs/agent-skills -g

# List project/global skills
polymcp skills list
polymcp skills list -g
```

Python agents auto-load skills from:
- `./.agents/skills`
- `./.skills`
- `~/.agents/skills`

If no project skills are found, the agent prints:

```text
[WARN] No project skills found in .agents/skills or .skills.
Use global skills: polymcp skills add vercel-labs/agent-skills -g
Or local skills: polymcp skills add vercel-labs/agent-skills
```

All extra flags/args are passed through to the underlying skills.sh CLI.

Overrides:
- set `POLYMCP_SKILLS_BIN` or `SKILLS_CLI` to point to a custom skills binary
- pass `--bin "path/to/skills"` to override for a single command

### `polymcp config`

```bash
polymcp config show
polymcp config set default_llm openai
polymcp config get default_llm
polymcp config path
```

### `polymcp inspector`

```bash
polymcp inspector
polymcp inspector --secure --api-key "your-strong-key"
```

## Notes

- local config and registry are stored in `~/.polymcp/`
- HTTP and stdio servers can be combined in one agent workflow

## License

MIT
