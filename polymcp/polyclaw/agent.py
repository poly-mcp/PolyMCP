"""
PolyClaw Agent.

Shell-first autonomous agent inspired by VURP, specialized for PolyMCP workflows.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import date
import hashlib
from html import unescape
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from typing import List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

from ..polyagent.llm_providers import LLMProvider


_SHELL_BLOCK_RE = re.compile(r"```(?:SHELL|shell|bash|sh)\s*\r?\n(.*?)```", re.DOTALL)
_FINAL_BLOCK_RE = re.compile(r"```(?:FINAL|final)\s*\r?\n(.*?)```", re.DOTALL)
_COMMON_SHELL_COMMANDS = {
    "ls",
    "dir",
    "find",
    "rg",
    "grep",
    "cat",
    "head",
    "tail",
    "wc",
    "echo",
    "pwd",
    "cd",
    "python",
    "python3",
    "pip",
    "pip3",
    "git",
    "docker",
    "npm",
    "pnpm",
    "yarn",
    "curl",
    "wget",
    "sed",
    "awk",
    "xargs",
    "sort",
    "uniq",
    "stat",
    "tree",
}
_MCP_INTENT_HINTS = (
    "mcp",
    "polymcp",
    "server",
    "registry",
    "list_tools",
    "invoke",
    "stdio",
    "/mcp",
    "tool",
)
_RESEARCH_INTENT_HINTS = (
    "best",
    "miglior",
    "ristorante",
    "restaurant",
    "news",
    "notizie",
    "search",
    "ricerca",
    "trova",
    "meteo",
    "weather",
    "prezzo",
    "price",
    "who is",
    "chi e",
    "quale",
    "dimmi",
)
_ALLOWED_INTENTS = ("research", "execution", "mcp_orchestration")
_REMOVAL_CLAIM_PATTERNS: Sequence[str] = (
    r"\brimoss[oaie]\b",
    r"\beliminat[oaie]\b",
    r"\brimozion[ea]\b",
    r"\bdeleted?\b",
    r"\bremoved?\b",
)


@dataclass
class PolyClawConfig:
    """Configuration for PolyClawAgent."""

    max_iterations: int = 24
    command_timeout: float = 300.0
    max_output_chars: int = 12000
    max_history_chars: int = 70000
    verbose: bool = False
    allow_dangerous_commands: bool = False
    use_docker: bool = True
    docker_image: str = "python:3.11-slim"
    docker_workspace: str = "/workspace"
    docker_enable_network: bool = True
    docker_start_timeout: float = 300.0
    docker_stop_timeout: float = 30.0
    docker_run_args: List[str] = field(default_factory=list)
    intent: str = "auto"
    allow_bootstrap: bool = True
    strict_no_setup: bool = False
    confirm_delete_commands: bool = True
    research_web_attempts: int = 3
    research_result_limit: int = 6
    no_command_patience: int = 4
    command_recovery_attempts: int = 2
    max_stagnant_steps: int = 2
    live_mode: bool = False
    live_max_output_lines: int = 20


class PolyClawAgent:
    """
    Autonomous shell-driven agent.

    The model proposes shell commands in fenced blocks and PolyClaw executes them,
    feeds outputs back to the model, and iterates until completion.
    """

    SYSTEM_PROMPT = """You are PolyClaw, an autonomous execution agent for PolyMCP.

Mission:
- Receive a user goal.
- Execute the work end-to-end.
- Prefer concrete actions over asking questions.
- You are autonomous and resourceful: try, inspect output, adapt strategy, and continue.
- Use shell commands, PolyMCP CLI, network requests, and file operations whenever useful.
- If needed, you may create or configure MCP components to solve the user task.
- Keep a human tone in visible messages (THINK/SAY) and explain decisions briefly.
- As soon as the goal is achieved, stop executing commands and emit FINAL immediately.
- Never invent command outputs or external facts.

PolyMCP CLI quick reference:
- polymcp init <name> --type http-server|stdio-server|agent --with-examples
- polymcp server add <url> --name <name>
- polymcp server list
- polymcp test server <url>
- polymcp test tool <url> <tool_name> --params '{"k":"v"}'
- polymcp agent run --type unified|codemode|basic

Runtime notes:
- Your shell commands run inside a Docker container.
- Workspace is mounted at /workspace.
- Changes in /workspace persist on host filesystem.

Response format rules:
1) If commands are needed, output one or more shell blocks:
```bash
command here
```
2) If the task is complete, output:
```FINAL
final user-facing answer with concrete results
```
3) Before shell blocks, include short operational lines in plain text:
THINK: what you are about to do (1 sentence)
SAY: what you are doing for the user (1 sentence)
4) Never output fake command results.
5) Keep commands idempotent when possible.
6) Never output placeholder text like "clear final answer for the user".
7) Do not repeat the same command with the same expected outcome multiple times.
8) For execution tasks, THINK/SAY alone is invalid: always include at least one ```bash block.
"""

    _FINAL_PLACEHOLDER_PATTERNS: Sequence[str] = (
        "clear final answer for the user",
        "final user-facing answer with concrete results",
        "your final answer here",
    )

    _DANGEROUS_COMMAND_PATTERNS: Sequence[Tuple[str, str]] = (
        (r"\bgit\s+reset\s+--hard\b", "blocked dangerous git reset --hard"),
        (r"\bgit\s+clean\s+-[a-z]*f[a-z]*\b", "blocked dangerous git clean"),
        (r"\brm\s+-rf\s+/(?:\s|$)", "blocked dangerous rm -rf /"),
        (r"\brm\s+-rf\s+~(?:\s|$)", "blocked dangerous rm -rf ~"),
        (r"\bmkfs(\.[a-z0-9]+)?\b", "blocked dangerous filesystem formatting"),
        (r"\bdd\s+if=.*\bof=/dev/", "blocked dangerous direct disk write"),
        (r"\bshutdown\b|\breboot\b|\bpoweroff\b", "blocked shutdown/reboot command"),
        (r":\(\)\s*\{:\|\:&\};:", "blocked fork bomb pattern"),
    )
    _BOOTSTRAP_COMMAND_PATTERNS: Sequence[Tuple[str, str]] = (
        (r"\bpip3?\s+install\b", "blocked bootstrap install command"),
        (r"\bpython3?\s+-m\s+pip\s+install\b", "blocked bootstrap install command"),
        (r"\buv\s+pip\s+install\b", "blocked bootstrap install command"),
        (r"\bapt(?:-get)?\s+install\b", "blocked bootstrap install command"),
        (r"\byum\s+install\b", "blocked bootstrap install command"),
        (r"\bdnf\s+install\b", "blocked bootstrap install command"),
        (r"\bapk\s+add\b", "blocked bootstrap install command"),
        (r"\bbrew\s+install\b", "blocked bootstrap install command"),
        (r"\bnpm\s+install\b", "blocked bootstrap install command"),
        (r"\bpnpm\s+add\b", "blocked bootstrap install command"),
        (r"\byarn\s+add\b", "blocked bootstrap install command"),
    )
    _DELETE_COMMAND_PATTERNS: Sequence[str] = (
        r"(^|[;&|]\s*)rm\s+",
        r"(^|[;&|]\s*)rmdir\s+",
        r"(^|[;&|]\s*)unlink\s+",
        r"\bfind\b[^\n;]*\s-delete\b",
        r"(^|[;&|]\s*)del\s+",
        r"(^|[;&|]\s*)erase\s+",
    )

    def __init__(
        self,
        llm_provider: LLMProvider,
        mcp_servers: Optional[List[str]] = None,
        config: Optional[PolyClawConfig] = None,
        verbose: bool = False,
    ):
        self.llm = llm_provider
        self.config = config or PolyClawConfig(verbose=verbose)
        if verbose:
            self.config.verbose = True
            self.config.live_mode = True
        self.mcp_servers = list(mcp_servers or [])
        self._history: List[str] = []
        self._docker_container_name: Optional[str] = None
        self._intent: str = "execution"
        self._delete_confirmation_mode: str = "ask"

    def run(self, user_message: str) -> str:
        """Run PolyClaw for a user request."""
        self._history = []
        self._delete_confirmation_mode = "ask"
        self._intent = self._resolve_intent(user_message)
        no_command_turns = 0
        blocked_only_steps = 0
        last_step_fingerprint: Optional[str] = None
        stagnant_steps = 0
        delete_commands_executed = 0
        delete_commands_blocked = 0

        try:
            if self.config.live_mode:
                self._live_status(f"intent selected: {self._intent}")
            self._add_history(f"[SYSTEM] Intent selected: {self._intent}")

            if self._should_answer_research_direct():
                if self.config.live_mode:
                    self._live_status(
                        "research mode without tool access, trying built-in web retrieval without shell"
                    )
                return self._run_research_without_servers(user_message)

            if self.config.use_docker:
                self._start_docker_container()

            for step in range(1, self.config.max_iterations + 1):
                if self.config.live_mode:
                    self._live_status(
                        f"step {step}/{self.config.max_iterations} started "
                        f"({self._runtime_label()})"
                    )

                prompt = self._build_prompt(user_message=user_message, step=step)
                try:
                    llm_response = self.llm.generate(prompt, temperature=0.1).strip()
                except Exception as exc:
                    return f"PolyClaw failed to contact the LLM: {exc}"
                text, commands, final_text = self._parse_response(llm_response)

                if self.config.verbose:
                    print(f"[polyclaw] step={step} commands={len(commands)}")
                    if text:
                        print(f"[polyclaw] note: {text[:240]}")
                if self.config.live_mode and text:
                    self._live_model_text(text)

                self._add_history(f"[STEP {step}] model\n{llm_response}")

                if not commands and not final_text:
                    recover_threshold = max(1, int(self.config.command_recovery_attempts))
                    if no_command_turns < recover_threshold:
                        recovered_commands, recovered_final, recovered_raw = self._recover_commands(
                            user_message=user_message,
                            step=step,
                        )
                        if recovered_raw:
                            self._add_history(f"[STEP {step}] recovery_model\n{recovered_raw}")
                        if recovered_final and not final_text:
                            final_text = recovered_final
                        if recovered_commands:
                            commands = recovered_commands
                            if self.config.live_mode:
                                self._live_status("recovered missing shell commands")

                if not commands:
                    no_command_turns += 1
                    if final_text:
                        if self._is_placeholder_final(final_text):
                            if self.config.live_mode:
                                self._live_status("placeholder FINAL detected, forcing continuation")
                            self._add_history(
                                "[SYSTEM] Invalid FINAL placeholder detected. Continue with real commands/results."
                            )
                            continue
                        if self.config.live_mode:
                            self._live_status("task completed by FINAL block")
                        return self._final_with_safety_note(
                            final_text=final_text.strip(),
                            delete_commands_executed=delete_commands_executed,
                            delete_commands_blocked=delete_commands_blocked,
                        )
                    if not commands:
                        if no_command_turns >= max(1, int(self.config.no_command_patience)):
                            if self.config.live_mode:
                                self._live_status("no actions produced repeatedly, generating summary")
                            return self._final_with_safety_note(
                                final_text=self._summarize_run(
                                    user_message,
                                    reason=(
                                        "Model returned no executable commands for multiple consecutive steps."
                                    ),
                                ),
                                delete_commands_executed=delete_commands_executed,
                                delete_commands_blocked=delete_commands_blocked,
                            )
                        self._add_history(
                            "[SYSTEM] No shell commands emitted. Continue with concrete commands or FINAL block."
                        )
                        if self.config.live_mode:
                            self._live_status("no command emitted, asking model to continue")
                        continue

                no_command_turns = 0
                command_results: List[str] = []
                blocked_this_step = 0

                for index, command_block in enumerate(commands, start=1):
                    command_block = command_block.strip()
                    if not command_block:
                        continue

                    policy_reason = self._find_policy_violation_reason(command_block)
                    if policy_reason:
                        blocked_this_step += 1
                        blocked_output = f"[POLICY BLOCKED] {policy_reason}\n{command_block}"
                        if self.config.live_mode:
                            self._live_status(f"policy blocked command {index}: {policy_reason}")
                        command_results.append(
                            f"$ [blocked command {index}]\n{blocked_output}\n[exit code: 125]"
                        )
                        if self._requires_delete_confirmation(command_block):
                            delete_commands_blocked += 1
                        continue

                    danger_reason = self._find_dangerous_command_reason(command_block)
                    if danger_reason and not self.config.allow_dangerous_commands:
                        blocked_output = f"[BLOCKED] {danger_reason}\n{command_block}"
                        if self.config.live_mode:
                            self._live_status(f"blocked command {index}: {danger_reason}")
                        command_results.append(
                            f"$ [blocked command {index}]\n{blocked_output}\n[exit code: 126]"
                        )
                        if self._requires_delete_confirmation(command_block):
                            delete_commands_blocked += 1
                        continue

                    if self.config.confirm_delete_commands and self._requires_delete_confirmation(
                        command_block
                    ):
                        if self._delete_confirmation_mode == "always_deny":
                            is_confirmed = False
                        elif self._delete_confirmation_mode == "always_allow":
                            is_confirmed = True
                        else:
                            is_confirmed = self._request_delete_confirmation(
                                command_block=command_block,
                                step=step,
                                index=index,
                            )
                        if not is_confirmed:
                            blocked_this_step += 1
                            blocked_output = (
                                "[BLOCKED] destructive delete command not confirmed by user\n"
                                f"{command_block}"
                            )
                            command_results.append(
                                f"$ [blocked command {index}]\n{blocked_output}\n[exit code: 125]"
                            )
                            delete_commands_blocked += 1
                            if self.config.live_mode:
                                self._live_status(f"delete command {index} denied by user")
                            continue

                    if self.config.live_mode:
                        self._live_command(step=step, index=index, command=command_block)
                    output, exit_code, elapsed = self._run_shell(command_block)
                    if self._requires_delete_confirmation(command_block):
                        delete_commands_executed += 1
                    command_results.append(
                        f"$ [command {index}]\n{command_block}\n{output}\n[exit code: {exit_code}]"
                    )
                    if self.config.live_mode:
                        self._live_output(exit_code=exit_code, elapsed=elapsed, output=output)

                    if self.config.verbose:
                        print(f"[polyclaw] command={index} exit={exit_code} elapsed={elapsed:.1f}s")

                if commands and blocked_this_step == len(commands):
                    blocked_only_steps += 1
                    self._add_history(
                        "[SYSTEM] All proposed commands were blocked by policy. "
                        "Propose policy-compliant commands or return FINAL."
                    )
                    if self.config.live_mode:
                        self._live_status(
                            f"policy-only step detected ({blocked_only_steps}/2), requesting compliant replan"
                        )
                    if blocked_only_steps >= 2:
                        return self._final_with_safety_note(
                            final_text=self._summarize_run(
                                user_message,
                                reason=(
                                    "Model repeatedly proposed commands blocked by policy. "
                                    "Need policy-compliant plan or direct FINAL."
                                ),
                            ),
                            delete_commands_executed=delete_commands_executed,
                            delete_commands_blocked=delete_commands_blocked,
                        )
                else:
                    blocked_only_steps = 0

                if command_results:
                    self._add_history("[STEP RESULT]\n" + "\n\n".join(command_results))
                    step_fingerprint = self._compute_step_fingerprint(commands, command_results)
                    if step_fingerprint == last_step_fingerprint:
                        stagnant_steps += 1
                        self._add_history(
                            "[SYSTEM] Repeated identical commands/output detected. "
                            "Finalize with a concrete FINAL answer."
                        )
                        if self.config.live_mode:
                            self._live_status(
                                f"stagnation detected ({stagnant_steps}/{self.config.max_stagnant_steps})"
                            )
                        if stagnant_steps >= self.config.max_stagnant_steps:
                            if self.config.live_mode:
                                self._live_status("stagnation threshold reached, generating summary")
                            return self._final_with_safety_note(
                                final_text=self._summarize_run(
                                    user_message,
                                    reason="Repeated commands with unchanged outputs.",
                                ),
                                delete_commands_executed=delete_commands_executed,
                                delete_commands_blocked=delete_commands_blocked,
                            )
                    else:
                        stagnant_steps = 0
                    last_step_fingerprint = step_fingerprint

                if final_text:
                    if self._is_placeholder_final(final_text):
                        if self.config.live_mode:
                            self._live_status("placeholder FINAL detected, forcing continuation")
                        self._add_history(
                            "[SYSTEM] Invalid FINAL placeholder detected. Continue with real commands/results."
                        )
                        continue
                    if self.config.live_mode:
                        self._live_status("task completed by FINAL block")
                    return self._final_with_safety_note(
                        final_text=final_text.strip(),
                        delete_commands_executed=delete_commands_executed,
                        delete_commands_blocked=delete_commands_blocked,
                    )

            if self.config.live_mode:
                self._live_status("iteration budget exhausted, generating final summary")
            return self._final_with_safety_note(
                final_text=self._summarize_run(
                    user_message,
                    reason="Iteration budget exhausted before receiving FINAL block.",
                ),
                delete_commands_executed=delete_commands_executed,
                delete_commands_blocked=delete_commands_blocked,
            )
        except Exception as exc:
            return f"PolyClaw runtime error: {exc}"
        finally:
            self._stop_docker_container()

    async def run_async(self, user_message: str) -> str:
        """Async wrapper for CLI compatibility."""
        return self.run(user_message)

    def _build_prompt(self, user_message: str, step: int) -> str:
        servers = ", ".join(self.mcp_servers) if self.mcp_servers else "(none configured)"
        history_text = "\n\n".join(self._history)
        runtime = "Docker container" if self.config.use_docker else "host shell"
        intent_guidance = self._intent_guidance()

        if len(history_text) > self.config.max_history_chars:
            history_text = history_text[-self.config.max_history_chars :]

        return (
            f"{self.SYSTEM_PROMPT}\n\n"
            f"Execution intent: {self._intent}\n"
            f"Intent guidance:\n{intent_guidance}\n\n"
            f"Runtime: {runtime}\n"
            f"Working directory: {os.getcwd()}\n"
            f"Configured MCP servers: {servers}\n"
            f"Current step: {step}/{self.config.max_iterations}\n\n"
            f"User goal:\n{user_message}\n\n"
            f"Execution history:\n{history_text if history_text else '(no history yet)'}\n\n"
            "Produce the next action now."
        )

    def _parse_response(self, response: str) -> Tuple[str, List[str], str]:
        final_match = _FINAL_BLOCK_RE.search(response)
        if final_match:
            final_text = final_match.group(1).strip()
        else:
            partial_final = re.search(r"```(?:FINAL|final)\s*\r?\n(.*)\Z", response, re.DOTALL)
            final_text = partial_final.group(1).strip() if partial_final else ""

        commands = [block.strip() for block in _SHELL_BLOCK_RE.findall(response) if block.strip()]

        text = _SHELL_BLOCK_RE.sub("", response)
        text = _FINAL_BLOCK_RE.sub("", text)
        if not final_match and final_text:
            text = re.sub(r"```(?:FINAL|final)\s*\r?\n.*\Z", "", text, flags=re.DOTALL)
        text = text.strip()

        return text, commands, final_text

    def _recover_commands(self, user_message: str, step: int) -> Tuple[List[str], str, str]:
        prompt = (
            "You failed to emit executable shell blocks.\n"
            "Produce ONLY one of:\n"
            "1) one or more fenced ```bash blocks with concrete commands, OR\n"
            "2) one fenced ```FINAL block if no command is needed.\n"
            "No THINK, no SAY, no explanations.\n\n"
            f"User goal:\n{user_message}\n"
            f"Current step: {step}\n"
            f"Working directory: {os.getcwd()}\n"
        )
        try:
            raw = self.llm.generate(prompt, temperature=0).strip()
        except Exception:
            return [], "", ""

        _, commands, final_text = self._parse_response(raw)
        if not commands:
            commands = self._extract_inline_commands(raw)
        return commands, final_text, raw

    def _extract_inline_commands(self, text: str) -> List[str]:
        collected: List[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lower = line.lower()
            if lower.startswith("think:") or lower.startswith("say:") or lower.startswith("final"):
                continue
            if line.startswith("$ "):
                line = line[2:].strip()
            if self._looks_like_shell_command(line):
                collected.append(line)
        if not collected:
            return []
        return ["\n".join(collected)]

    def _looks_like_shell_command(self, line: str) -> bool:
        token = line.strip().split(" ", 1)[0]
        token = token.strip()
        if not token:
            return False
        if token in _COMMON_SHELL_COMMANDS:
            return True
        if token.startswith("./") or token.startswith("../") or token.startswith("/"):
            return True
        if any(sym in line for sym in ("|", ">", "<", "&&", "||", ";")):
            if re.match(r"^[a-zA-Z0-9._/-]+$", token):
                return True
        return False

    def _runtime_label(self) -> str:
        return "docker" if self.config.use_docker else "host"

    def _live_status(self, message: str) -> None:
        print(f"[POLYCLAW][STATUS] {message}", flush=True)

    def _live_model_text(self, text: str) -> None:
        thoughts: List[str] = []
        says: List[str] = []
        neutral: List[str] = []

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lower = line.lower()
            if lower.startswith("think:"):
                thoughts.append(line.split(":", 1)[1].strip())
            elif lower.startswith("say:"):
                says.append(line.split(":", 1)[1].strip())
            else:
                neutral.append(line)

        for item in thoughts:
            print(f"[POLYCLAW][THINK] {item}", flush=True)
        for item in says:
            print(f"[POLYCLAW][SAY] {item}", flush=True)
        for item in neutral:
            print(f"[POLYCLAW][NOTE] {item}", flush=True)

    def _live_command(self, step: int, index: int, command: str) -> None:
        print(f"[POLYCLAW][ACTION][step={step} cmd={index}]", flush=True)
        for line in command.splitlines():
            print(f"$ {line}", flush=True)

    def _live_output(self, exit_code: int, elapsed: float, output: str) -> None:
        print(f"[POLYCLAW][OUTPUT] exit={exit_code} elapsed={elapsed:.1f}s", flush=True)
        lines = output.splitlines()
        limit = max(1, int(self.config.live_max_output_lines))
        preview = lines[:limit]
        for line in preview:
            print(f"  {line}", flush=True)
        if len(lines) > limit:
            print(f"  ... ({len(lines) - limit} more lines)", flush=True)

    def _is_placeholder_final(self, final_text: str) -> bool:
        normalized = re.sub(r"\s+", " ", final_text.strip().lower())
        return any(normalized == p for p in self._FINAL_PLACEHOLDER_PATTERNS)

    def _find_dangerous_command_reason(self, command_block: str) -> Optional[str]:
        lowered = command_block.lower()
        for pattern, reason in self._DANGEROUS_COMMAND_PATTERNS:
            if re.search(pattern, lowered):
                return reason
        return None

    def _requires_delete_confirmation(self, command_block: str) -> bool:
        lowered = command_block.lower()
        for pattern in self._DELETE_COMMAND_PATTERNS:
            if re.search(pattern, lowered, flags=re.MULTILINE):
                return True
        return False

    def _request_delete_confirmation(self, command_block: str, step: int, index: int) -> bool:
        preview = command_block.strip().replace("\n", " ; ")
        if len(preview) > 220:
            preview = preview[:220] + "..."

        if self.config.live_mode:
            self._live_status(f"delete confirmation required for step={step} cmd={index}")

        if not (sys.stdin and hasattr(sys.stdin, "isatty") and sys.stdin.isatty()):
            self._add_history(
                "[SYSTEM] Delete confirmation required but no interactive TTY is available."
            )
            self._delete_confirmation_mode = "always_deny"
            return False

        try:
            answer = input(
                f"[POLYCLAW][CONFIRM] Eseguire comando distruttivo? [y/N/a/x]\n"
                f"  y=yes, n=no (blocca i prossimi delete), a=sempre si, x=sempre no\n"
                f"  step={step} cmd={index}: {preview}\n> "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            self._delete_confirmation_mode = "always_deny"
            return False

        if answer in {"a", "all", "always", "sempre"}:
            self._delete_confirmation_mode = "always_allow"
            return True

        if answer in {"x", "never", "mai", "noall"}:
            self._delete_confirmation_mode = "always_deny"
            return False

        if answer in {"y", "yes", "s", "si"}:
            return True

        # Default n/N behavior: deny now and deny all further delete commands in this run.
        self._delete_confirmation_mode = "always_deny"
        return False

    def _find_policy_violation_reason(self, command_block: str) -> Optional[str]:
        lowered = command_block.lower()

        if self.config.strict_no_setup and self._intent != "mcp_orchestration":
            if re.search(r"\bpolymcp\b", lowered):
                return "polymcp CLI blocked for non-MCP intent"

        if not self.config.allow_bootstrap:
            for pattern, reason in self._BOOTSTRAP_COMMAND_PATTERNS:
                if re.search(pattern, lowered):
                    return f"{reason} (use --allow-bootstrap to enable)"

        if self.config.strict_no_setup and self._intent == "research":
            if re.search(r"\b(polymcp\s+init|git\s+clone)\b", lowered):
                return "project scaffolding blocked for research intent"

        return None

    def _resolve_intent(self, user_message: str) -> str:
        configured_intent = (self.config.intent or "auto").strip().lower()

        if configured_intent == "mcp":
            return "mcp_orchestration"
        if configured_intent in _ALLOWED_INTENTS:
            return configured_intent
        if configured_intent != "auto":
            return "execution"

        llm_intent = self._infer_intent_with_llm(user_message)
        if llm_intent:
            return llm_intent
        return self._infer_intent_with_rules(user_message)

    def _infer_intent(self, user_message: str) -> str:
        """Backward-compatible alias."""
        return self._infer_intent_with_rules(user_message)

    def _infer_intent_with_rules(self, user_message: str) -> str:
        text = user_message.strip().lower()

        if any(hint in text for hint in _MCP_INTENT_HINTS):
            return "mcp_orchestration"

        if any(hint in text for hint in _RESEARCH_INTENT_HINTS):
            return "research"

        if re.search(r"\bhttps?://", text):
            return "execution"

        return "execution"

    def _infer_intent_with_llm(self, user_message: str) -> Optional[str]:
        prompt = (
            "Classify the user request intent for an autonomous shell agent.\n"
            "Return ONLY one label from: research | execution | mcp_orchestration.\n\n"
            "Label meaning:\n"
            "- research: information/recommendation/search questions.\n"
            "- execution: file/system/task execution not specifically about MCP setup.\n"
            "- mcp_orchestration: requests explicitly about MCP servers, tools, registry, or PolyMCP setup.\n\n"
            f"User request:\n{user_message}\n"
        )
        try:
            raw = self.llm.generate(prompt, temperature=0).strip().lower()
        except Exception:
            return None

        normalized = raw.replace("`", "").strip()
        if normalized == "mcp":
            return "mcp_orchestration"
        if "mcp" in normalized and "orchestration" not in normalized:
            return "mcp_orchestration"
        for token in _ALLOWED_INTENTS:
            if token in normalized:
                return token
        return None

    def _intent_guidance(self) -> str:
        if self._intent == "research":
            return (
                "- Prefer information retrieval and synthesis.\n"
                "- Use practical retrieval strategies (HTTP, APIs, scraping, tools) and adapt if one fails.\n"
                "- If strict mode is enabled and no tool/server access exists, use built-in web retrieval.\n"
                "- Use PolyMCP setup only if it clearly helps solve the request.\n"
                "- Use installs only when they are necessary for progress.\n"
                "- If reliable evidence is insufficient, report limits clearly in FINAL."
            )
        if self._intent == "mcp_orchestration":
            return (
                "- Focus on MCP orchestration/build/runbook execution.\n"
                "- Use PolyMCP CLI as needed.\n"
                "- Keep actions minimal and stop once requested outcome is met."
            )
        return (
            "- Focus on direct task execution with minimal commands.\n"
            "- Avoid unrelated setup or scaffolding.\n"
            "- Stop and emit FINAL immediately after success criteria are met."
        )

    def _compute_step_fingerprint(self, commands: List[str], command_results: List[str]) -> str:
        normalized_commands = [" ".join(cmd.strip().split()) for cmd in commands if cmd.strip()]
        payload = "\n---\n".join(normalized_commands) + "\n====\n" + "\n---\n".join(command_results)
        return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()

    def _run_shell(self, command: str) -> Tuple[str, int, float]:
        if self.config.use_docker:
            return self._run_shell_in_docker(command)
        return self._run_shell_on_host(command)

    def _run_shell_on_host(self, command: str) -> Tuple[str, int, float]:
        started = time.time()
        kwargs = {
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "timeout": self.config.command_timeout,
        }

        try:
            if os.name != "nt":
                wrapped = self._with_bash_pipefail(command)
                result = subprocess.run(["/bin/bash", "-lc", wrapped], **kwargs)
            else:
                result = subprocess.run(command, shell=True, **kwargs)
            elapsed = time.time() - started
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                if output and not output.endswith("\n"):
                    output += "\n"
                output += result.stderr
            output = output.strip() or "(no output)"
            output = self._truncate_output(output)
            return output, int(result.returncode), elapsed
        except subprocess.TimeoutExpired:
            elapsed = time.time() - started
            return f"[TIMEOUT {self.config.command_timeout:.0f}s]", 124, elapsed
        except Exception as exc:
            elapsed = time.time() - started
            return f"[ERROR] {exc}", 1, elapsed

    def _start_docker_container(self) -> None:
        if self._docker_container_name:
            return

        docker_bin = shutil.which("docker")
        if not docker_bin:
            raise RuntimeError("Docker CLI not found in PATH")

        container_name = f"polyclaw-{uuid.uuid4().hex[:12]}"
        workspace_host = os.path.abspath(os.getcwd())
        workspace_mount = f"{workspace_host}:{self.config.docker_workspace}"

        cmd = [
            docker_bin,
            "run",
            "-d",
            "--rm",
            "--name",
            container_name,
            "-v",
            workspace_mount,
            "-w",
            self.config.docker_workspace,
            "-e",
            "PYTHONUNBUFFERED=1",
        ]

        if not self.config.docker_enable_network:
            cmd += ["--network", "none"]

        if self.config.docker_run_args:
            cmd += list(self.config.docker_run_args)

        cmd += [self.config.docker_image, "sleep", "infinity"]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.config.docker_start_timeout,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode != 0:
            err = (result.stderr or result.stdout or "unknown Docker error").strip()
            raise RuntimeError(f"Failed to start Docker container: {err}")

        self._docker_container_name = container_name
        if self.config.live_mode:
            self._live_status(f"docker container started: {container_name}")
        elif self.config.verbose:
            print(f"[polyclaw] docker container started: {container_name}")

    def _stop_docker_container(self) -> None:
        if not self._docker_container_name:
            return

        docker_bin = shutil.which("docker")
        if not docker_bin:
            self._docker_container_name = None
            return

        container_name = self._docker_container_name
        self._docker_container_name = None

        try:
            subprocess.run(
                [docker_bin, "stop", container_name],
                capture_output=True,
                text=True,
                timeout=self.config.docker_stop_timeout,
                encoding="utf-8",
                errors="replace",
            )
            if self.config.live_mode:
                self._live_status(f"docker container stopped: {container_name}")
            elif self.config.verbose:
                print(f"[polyclaw] docker container stopped: {container_name}")
        except Exception:
            pass

    def _run_shell_in_docker(self, command: str) -> Tuple[str, int, float]:
        if not self._docker_container_name:
            raise RuntimeError("Docker container is not running")

        docker_bin = shutil.which("docker")
        if not docker_bin:
            raise RuntimeError("Docker CLI not found in PATH")

        started = time.time()
        command_b64 = base64.b64encode(command.encode("utf-8", errors="replace")).decode("ascii")
        launcher = (
            "import base64, os, subprocess, sys; "
            "cmd = base64.b64decode(os.environ['POLYCLAW_CMD_B64']).decode('utf-8', 'replace'); "
            "wrapped = 'set -o pipefail\\n' + cmd; "
            "p = subprocess.run(['/bin/bash', '-lc', wrapped], text=True, capture_output=True); "
            "sys.stdout.write(p.stdout or ''); "
            "sys.stderr.write(p.stderr or ''); "
            "sys.exit(p.returncode)"
        )

        exec_cmd = [
            docker_bin,
            "exec",
            "-i",
            "-e",
            f"POLYCLAW_CMD_B64={command_b64}",
            self._docker_container_name,
            "python",
            "-c",
            launcher,
        ]

        try:
            result = subprocess.run(
                exec_cmd,
                capture_output=True,
                text=True,
                timeout=self.config.command_timeout,
                encoding="utf-8",
                errors="replace",
            )
            elapsed = time.time() - started
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                if output and not output.endswith("\n"):
                    output += "\n"
                output += result.stderr
            output = output.strip() or "(no output)"
            output = self._truncate_output(output)
            return output, int(result.returncode), elapsed
        except subprocess.TimeoutExpired:
            elapsed = time.time() - started
            return f"[TIMEOUT {self.config.command_timeout:.0f}s]", 124, elapsed
        except Exception as exc:
            elapsed = time.time() - started
            return f"[ERROR] {exc}", 1, elapsed

    def _truncate_output(self, output: str) -> str:
        if len(output) <= self.config.max_output_chars:
            return output
        head = output[: self.config.max_output_chars // 2]
        tail = output[-self.config.max_output_chars // 2 :]
        return f"{head}\n[...TRUNCATED...]\n{tail}"

    def _with_bash_pipefail(self, command: str) -> str:
        return f"set -o pipefail\n{command}"

    def _should_answer_research_direct(self) -> bool:
        if self._intent != "research":
            return False
        if not self.config.strict_no_setup:
            return False
        if self.mcp_servers:
            return False
        return True

    def _run_research_without_servers(self, user_message: str) -> str:
        results = self._search_web_results(user_message)
        if results:
            if self.config.live_mode:
                self._live_status(f"built-in web retrieval succeeded with {len(results)} sources")
            evidence_lines = []
            for idx, (title, url, snippet) in enumerate(results, start=1):
                line = f"{idx}. {title} | {url}"
                if snippet:
                    line += f" | {snippet}"
                evidence_lines.append(line)
            self._add_history("[RESEARCH EVIDENCE]\n" + "\n".join(evidence_lines))
            return self._generate_research_grounded_final(user_message, results)

        if self.config.live_mode:
            self._live_status("built-in web retrieval failed, returning limitation-aware answer")
        return self._generate_research_final(user_message)

    def _search_web_results(self, user_message: str) -> List[Tuple[str, str, str]]:
        attempts = max(1, int(self.config.research_web_attempts))
        limit = max(1, int(self.config.research_result_limit))

        base = user_message.strip()
        queries = [base, f"{base} recensioni", f"{base} tripadvisor", f"{base} michelin"]

        collected: List[Tuple[str, str, str]] = []
        seen_urls = set()

        for query in queries[:attempts]:
            for title, url, snippet in self._fetch_duckduckgo_results(query=query, limit=limit):
                key = url.strip().lower()
                if not key or key in seen_urls:
                    continue
                seen_urls.add(key)
                collected.append((title, url, snippet))
                if len(collected) >= limit:
                    return collected

        return collected

    def _fetch_duckduckgo_results(self, query: str, limit: int) -> List[Tuple[str, str, str]]:
        endpoints = [
            f"https://duckduckgo.com/html/?q={quote_plus(query)}",
            f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
        ]
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/121.0 Safari/537.36"
            )
        }
        link_re = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        snippet_re = re.compile(
            r'<(?:a|div)[^>]*class="result__snippet"[^>]*>(.*?)</(?:a|div)>',
            re.IGNORECASE | re.DOTALL,
        )

        for endpoint in endpoints:
            try:
                req = Request(endpoint, headers=headers)
                with urlopen(req, timeout=min(float(self.config.command_timeout), 20.0)) as resp:
                    html = resp.read().decode("utf-8", errors="replace")
            except Exception:
                continue

            anchors = link_re.findall(html)
            snippets = snippet_re.findall(html)
            rows: List[Tuple[str, str, str]] = []

            for idx, (raw_href, raw_title) in enumerate(anchors):
                url = self._normalize_search_url(raw_href)
                if not url:
                    continue
                title = self._strip_html(raw_title)
                snippet = self._strip_html(snippets[idx]) if idx < len(snippets) else ""
                if title:
                    rows.append((title, url, snippet))
                if len(rows) >= limit:
                    return rows

            if rows:
                return rows

        return []

    def _normalize_search_url(self, raw_href: str) -> str:
        href = unescape(raw_href or "").strip()
        if not href:
            return ""

        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/l/?"):
            href = "https://duckduckgo.com" + href

        if "duckduckgo.com/l/?" in href:
            parsed = urlparse(href)
            uddg = parse_qs(parsed.query).get("uddg", [None])[0]
            if uddg:
                href = unquote(uddg)

        if not href.startswith("http://") and not href.startswith("https://"):
            return ""
        return href

    def _strip_html(self, value: str) -> str:
        text = re.sub(r"<[^>]+>", " ", value or "")
        text = unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    def _generate_research_grounded_final(
        self,
        user_message: str,
        results: List[Tuple[str, str, str]],
    ) -> str:
        today = date.today().isoformat()
        evidence_lines = []
        for idx, (title, url, snippet) in enumerate(results, start=1):
            line = f"{idx}. {title} | {url}"
            if snippet:
                line += f" | snippet: {snippet}"
            evidence_lines.append(line)

        prompt = (
            "Rispondi in italiano con un risultato concreto e verificabile.\n"
            "Usa SOLO le evidenze fornite qui sotto; non inventare nomi, rating o fonti.\n"
            "Se 'migliore' non e' oggettivo, proponi una prima scelta motivata e due alternative.\n"
            "Chiudi con una sezione 'Fonti:' contenente 2-5 URL presi dalle evidenze.\n"
            "Nessun blocco di codice.\n\n"
            f"Oggi: {today}\n"
            f"Richiesta utente:\n{user_message}\n\n"
            f"Evidenze web raccolte:\n{chr(10).join(evidence_lines)}\n"
        )
        try:
            return self.llm.generate(prompt, temperature=0.2).strip()
        except Exception:
            top_title, top_url, _ = results[0]
            return (
                "Non posso determinare con certezza assoluta un singolo migliore, ma dalla ricerca web "
                f"la prima fonte utile e': {top_title} ({top_url})."
            )

    def _generate_research_final(self, user_message: str) -> str:
        today = date.today().isoformat()
        return (
            "Ho provato a recuperare risultati web verificabili ma non sono riuscito a ottenere fonti affidabili "
            f"(data: {today}). Per evitare risposte inventate non posso indicare un risultato 'vero' in questo momento.\n"
            "Se vuoi un risultato verificato, collega un MCP server/tool di ricerca web e rilancio subito la richiesta:\n"
            f"- richiesta: {user_message}"
        )

    def _summarize_run(self, user_message: str, reason: Optional[str] = None) -> str:
        history_text = "\n\n".join(self._history[-20:])
        reason_text = reason or "General completion summary."
        prompt = (
            "Create a concise final user-facing report in Italian.\n"
            "Describe what was completed, what failed, and next concrete action.\n"
            "Do not invent results.\n\n"
            f"Why summary is needed:\n{reason_text}\n\n"
            f"User goal:\n{user_message}\n\n"
            f"Execution log:\n{history_text if history_text else '(no execution log)'}"
        )
        try:
            return self.llm.generate(prompt, temperature=0.1).strip()
        except Exception:
            return (
                "PolyClaw could not produce a final summary from the execution log. "
                "Run again with a more specific goal."
            )

    def _add_history(self, item: str) -> None:
        self._history.append(item.strip())

    def _final_with_safety_note(
        self,
        final_text: str,
        delete_commands_executed: int,
        delete_commands_blocked: int,
    ) -> str:
        text = (final_text or "").strip()
        if not text:
            return text

        if delete_commands_executed > 0:
            return text

        if delete_commands_blocked <= 0:
            return text

        claims_removal = any(
            re.search(pattern, text, flags=re.IGNORECASE) for pattern in _REMOVAL_CLAIM_PATTERNS
        )
        safety_note = (
            "Nota sicurezza: nessuna rimozione e' stata eseguita "
            "(comandi delete negati o bloccati)."
        )

        if not claims_removal:
            if safety_note.lower() in text.lower():
                return text
            return f"{safety_note}\n\n{text}"

        filtered_lines: List[str] = []
        for line in text.splitlines():
            if any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in _REMOVAL_CLAIM_PATTERNS):
                continue
            filtered_lines.append(line)

        filtered_text = "\n".join(line for line in filtered_lines if line.strip()).strip()
        if filtered_text:
            return f"{safety_note}\n\n{filtered_text}"
        return safety_note
