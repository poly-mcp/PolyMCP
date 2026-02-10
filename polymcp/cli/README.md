<p align="center">
  <img src="polymcp-cli.png" alt="PolymCP CLI Logo" width="500"/>
</p>

<p align="center">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <img src="https://img.shields.io/badge/python-%3E%3D3.8-blue" alt="Python 3.8+">
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
polymcp agent run --query "Summarize latest server output"
polymcp agent benchmark --query "Add 2 and 2" --iterations 5
```

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
