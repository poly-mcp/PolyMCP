"""
PolyClaw tests.

Includes:
- deterministic host-runtime tests
- Docker runtime command-path test (mocked)
- opt-in real Docker integration test
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import List

import pytest

from polymcp.polyclaw import PolyClawAgent, PolyClawConfig
from polymcp.polyagent.llm_providers import LLMProvider


class ScriptedLLMProvider(LLMProvider):
    """Deterministic provider that returns scripted responses in sequence."""

    def __init__(self, responses: List[str]):
        self.responses = list(responses)
        self.calls = 0

    def generate(self, prompt: str, **kwargs) -> str:
        self.calls += 1
        if self.responses:
            return self.responses.pop(0)
        return "```FINAL\nNo scripted response left.\n```"


def test_polyclaw_host_runtime_executes_multistep(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    provider = ScriptedLLMProvider(
        [
            """Avvio.
```bash
mkdir -p artifacts
printf 'step-1\n' > artifacts/report.txt
```
""",
            """Continuo.
```bash
printf 'step-2\n' >> artifacts/report.txt
cat artifacts/report.txt
```
""",
            """```FINAL
Workflow completato. Report creato.
```""",
        ]
    )

    agent = PolyClawAgent(
        llm_provider=provider,
        config=PolyClawConfig(
            use_docker=False,
            verbose=False,
            intent="execution",
            max_iterations=5,
            command_timeout=30.0,
        ),
    )

    result = agent.run("Genera report a step e chiudi")

    report_path = tmp_path / "artifacts" / "report.txt"
    assert report_path.exists()
    assert report_path.read_text(encoding="utf-8") == "step-1\nstep-2\n"
    assert "Workflow completato" in result


def test_polyclaw_recovers_commands_when_missing_shell_blocks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    provider = ScriptedLLMProvider(
        [
            "THINK: conto i file.\nSAY: eseguo il conteggio.",
            """```bash
printf '3\n'
```""",
            """```FINAL
Conteggio completato.
```""",
        ]
    )

    agent = PolyClawAgent(
        llm_provider=provider,
        config=PolyClawConfig(
            use_docker=False,
            verbose=False,
            intent="execution",
            max_iterations=4,
        ),
    )

    result = agent.run("quanti file python ci sono?")

    assert "completato" in result.lower()
    assert any("[STEP 1] recovery_model" in entry for entry in agent._history)
    assert any("$ [command 1]" in entry for entry in agent._history)


def test_polyclaw_blocks_dangerous_commands(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    provider = ScriptedLLMProvider(
        [
            """```bash
rm -rf /
```
""",
            """```FINAL
Comando pericoloso bloccato correttamente.
```""",
        ]
    )

    agent = PolyClawAgent(
        llm_provider=provider,
        config=PolyClawConfig(
            use_docker=False,
            verbose=False,
            intent="execution",
            max_iterations=4,
            allow_dangerous_commands=False,
        ),
    )

    result = agent.run("Prova comando pericoloso")

    assert "bloccato" in result.lower()
    assert any("[BLOCKED]" in entry for entry in agent._history)


def test_polyclaw_delete_requires_confirmation_and_blocks_when_denied(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "to_remove.txt"
    target.write_text("data\n", encoding="utf-8")

    provider = ScriptedLLMProvider(
        [
            """```bash
rm -f to_remove.txt
```""",
            """```FINAL
Delete non autorizzato.
```""",
        ]
    )

    agent = PolyClawAgent(
        llm_provider=provider,
        config=PolyClawConfig(
            use_docker=False,
            verbose=False,
            intent="execution",
            confirm_delete_commands=True,
            max_iterations=4,
        ),
    )

    monkeypatch.setattr(agent, "_request_delete_confirmation", lambda **_: False)

    result = agent.run("rimuovi il file")

    assert "non autorizzato" in result.lower()
    assert target.exists()
    assert any(
        "destructive delete command not confirmed by user" in entry
        for entry in agent._history
    )


def test_polyclaw_delete_runs_when_confirmed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "to_remove.txt"
    target.write_text("data\n", encoding="utf-8")

    provider = ScriptedLLMProvider(
        [
            """```bash
rm -f to_remove.txt
```""",
            """```FINAL
Delete completato.
```""",
        ]
    )

    agent = PolyClawAgent(
        llm_provider=provider,
        config=PolyClawConfig(
            use_docker=False,
            verbose=False,
            intent="execution",
            confirm_delete_commands=True,
            max_iterations=4,
        ),
    )

    monkeypatch.setattr(agent, "_request_delete_confirmation", lambda **_: True)

    result = agent.run("rimuovi il file")

    assert "completato" in result.lower()
    assert not target.exists()


def test_polyclaw_delete_denied_mode_avoids_reprompt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.txt").write_text("a\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b\n", encoding="utf-8")

    provider = ScriptedLLMProvider(
        [
            """```bash
rm -f a.txt
```""",
            """```bash
rm -f b.txt
```""",
            """```FINAL
Fine.
```""",
        ]
    )

    agent = PolyClawAgent(
        llm_provider=provider,
        config=PolyClawConfig(
            use_docker=False,
            verbose=False,
            intent="execution",
            confirm_delete_commands=True,
            max_iterations=5,
        ),
    )

    agent._delete_confirmation_mode = "always_deny"
    monkeypatch.setattr(
        agent,
        "_request_delete_confirmation",
        lambda **_: (_ for _ in ()).throw(AssertionError("should not re-prompt")),
    )

    result = agent.run("rimuovi i file")

    assert "fine" in result.lower()
    assert (tmp_path / "a.txt").exists()
    assert (tmp_path / "b.txt").exists()


def test_polyclaw_denied_delete_rewrites_false_removal_final(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "to_remove.txt"
    target.write_text("data\n", encoding="utf-8")

    provider = ScriptedLLMProvider(
        [
            """```bash
rm -f to_remove.txt
```""",
            """```FINAL
Rimozione eseguita con successo.
```""",
        ]
    )

    agent = PolyClawAgent(
        llm_provider=provider,
        config=PolyClawConfig(
            use_docker=False,
            verbose=False,
            intent="execution",
            confirm_delete_commands=True,
            max_iterations=4,
        ),
    )

    monkeypatch.setattr(agent, "_request_delete_confirmation", lambda **_: False)

    result = agent.run("rimuovi il file")

    assert target.exists()
    assert "nessuna rimozione" in result.lower()
    assert "rimozione eseguita con successo" not in result.lower()


def test_polyclaw_parse_response_accepts_unclosed_final_block():
    agent = PolyClawAgent(
        llm_provider=ScriptedLLMProvider([]),
        config=PolyClawConfig(use_docker=False, verbose=False),
    )

    text, commands, final_text = agent._parse_response("```FINAL\nCompletato senza fence finale")

    assert text == ""
    assert commands == []
    assert "Completato senza fence finale" in final_text


def test_polyclaw_auto_intent_detects_research():
    agent = PolyClawAgent(
        llm_provider=ScriptedLLMProvider([]),
        config=PolyClawConfig(use_docker=False, verbose=False),
    )
    assert agent._infer_intent("mi dai il miglior ristorante di parma") == "research"
    assert agent._infer_intent("crea un server mcp e registra tools") == "mcp_orchestration"


def test_polyclaw_auto_intent_prefers_llm_label():
    provider = ScriptedLLMProvider(["research"])
    agent = PolyClawAgent(
        llm_provider=provider,
        config=PolyClawConfig(use_docker=False, verbose=False, intent="auto"),
    )
    assert agent._resolve_intent("fammi una raccomandazione") == "research"


def test_polyclaw_policy_blocks_polymcp_for_research_intent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    provider = ScriptedLLMProvider(
        [
            """```bash
polymcp server list
```
""",
            """```FINAL
Comando di setup bloccato correttamente.
```""",
        ]
    )

    agent = PolyClawAgent(
        llm_provider=provider,
        mcp_servers=["http://localhost:8000/mcp"],
        config=PolyClawConfig(
            use_docker=False,
            verbose=False,
            intent="research",
            strict_no_setup=True,
        ),
    )

    result = agent.run("mi dai il miglior ristorante di parma")

    assert "bloccato" in result.lower()
    assert any("[POLICY BLOCKED]" in entry for entry in agent._history)
    assert any("[exit code: 125]" in entry for entry in agent._history)


def test_polyclaw_policy_block_loop_summarizes_early(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    provider = ScriptedLLMProvider(
        [
            """```bash
polymcp server list
```""",
            """```bash
polymcp server list
```""",
            "Sintesi: i comandi proposti non rispettano la policy.",
        ]
    )

    agent = PolyClawAgent(
        llm_provider=provider,
        mcp_servers=["http://localhost:8000/mcp"],
        config=PolyClawConfig(
            use_docker=False,
            verbose=False,
            intent="research",
            strict_no_setup=True,
        ),
    )

    result = agent.run("consigliami un ristorante a parma")

    assert "policy" in result.lower()
    assert provider.calls == 3


def test_polyclaw_research_without_servers_uses_web_evidence_prompt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    provider = ScriptedLLMProvider(["Risposta basata su fonti web."])

    agent = PolyClawAgent(
        llm_provider=provider,
        config=PolyClawConfig(
            use_docker=False,
            verbose=False,
            intent="research",
            strict_no_setup=True,
        ),
    )

    monkeypatch.setattr(
        agent,
        "_search_web_results",
        lambda _query: [
            ("Top Parma Restaurants - Example", "https://example.com/parma", "snippet"),
            ("Best Osterie Parma - Example2", "https://example.org/osterie", "snippet2"),
        ],
    )

    result = agent.run("mi dai il miglior ristorante di parma")

    assert "Risposta basata su fonti web" in result
    assert provider.calls == 1
    assert not any("[STEP RESULT]" in entry for entry in agent._history)


def test_polyclaw_research_without_servers_falls_back_when_no_web_results(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    provider = ScriptedLLMProvider([])

    agent = PolyClawAgent(
        llm_provider=provider,
        config=PolyClawConfig(
            use_docker=False,
            verbose=False,
            intent="research",
            strict_no_setup=True,
        ),
    )

    monkeypatch.setattr(agent, "_search_web_results", lambda _query: [])

    result = agent.run("mi dai il miglior ristorante di parma")

    assert "fonti affidabili" in result
    assert provider.calls == 0
    assert not any("[STEP RESULT]" in entry for entry in agent._history)


def test_polyclaw_policy_blocks_bootstrap_install_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    provider = ScriptedLLMProvider(
        [
            """```bash
pip install polymcp
```
""",
            """```FINAL
Install non necessaria bloccata.
```""",
        ]
    )

    agent = PolyClawAgent(
        llm_provider=provider,
        config=PolyClawConfig(
            use_docker=False,
            verbose=False,
            intent="execution",
            allow_bootstrap=False,
        ),
    )

    result = agent.run("dimmi la versione corrente senza installare nulla")

    assert "bloccata" in result.lower()
    assert any("allow-bootstrap" in entry for entry in agent._history)


def test_polyclaw_mcp_intent_allows_polymcp_command(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    provider = ScriptedLLMProvider(
        [
            """```bash
polymcp server list
```
""",
            """```FINAL
Comando MCP eseguito.
```""",
        ]
    )

    agent = PolyClawAgent(
        llm_provider=provider,
        config=PolyClawConfig(
            use_docker=False,
            verbose=False,
            intent="mcp",
            strict_no_setup=True,
        ),
    )

    calls = []

    def fake_run_shell(command):
        calls.append(command)
        return "ok", 0, 0.1

    monkeypatch.setattr(agent, "_run_shell", fake_run_shell)

    result = agent.run("controlla i server mcp")

    assert "eseguito" in result.lower()
    assert calls == ["polymcp server list"]
    assert not any("[POLICY BLOCKED]" in entry for entry in agent._history)


def test_polyclaw_default_mode_is_permissive_for_setup_commands(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    provider = ScriptedLLMProvider(
        [
            """```bash
polymcp server list
```
""",
            """```FINAL
Permissive mode executed setup command.
```""",
        ]
    )

    agent = PolyClawAgent(
        llm_provider=provider,
        config=PolyClawConfig(
            use_docker=False,
            verbose=False,
            intent="research",
            strict_no_setup=False,
            allow_bootstrap=True,
        ),
    )

    calls = []

    def fake_run_shell(command):
        calls.append(command)
        return "ok", 0, 0.1

    monkeypatch.setattr(agent, "_run_shell", fake_run_shell)

    result = agent.run("trova il miglior ristorante di parma")

    assert "permissive mode" in result.lower()
    assert calls == ["polymcp server list"]
    assert not any("[POLICY BLOCKED]" in entry for entry in agent._history)


def test_polyclaw_stagnation_guard_prevents_iteration_exhaustion(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    provider = ScriptedLLMProvider(
        [
            """```bash
printf 'loop\n' >> loop.txt
cat loop.txt
```
""",
            """```bash
printf 'loop\n' >> loop.txt
cat loop.txt
```
""",
            "Sintesi automatica per stallo rilevato.",
        ]
    )

    agent = PolyClawAgent(
        llm_provider=provider,
        config=PolyClawConfig(
            use_docker=False,
            verbose=False,
            intent="execution",
            max_iterations=8,
            max_stagnant_steps=1,
        ),
    )

    result = agent.run("Esegui e chiudi appena stai ripetendo gli stessi passi")

    output_file = tmp_path / "loop.txt"
    assert output_file.exists()
    assert output_file.read_text(encoding="utf-8") == "loop\nloop\n"
    assert "stallo" in result.lower()
    assert provider.calls == 3


def test_polyclaw_uses_pipefail_for_pipeline_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    provider = ScriptedLLMProvider(
        [
            """```bash
__definitely_missing_command__ | cat
```
""",
            """```FINAL
Errore pipeline verificato.
```""",
        ]
    )

    agent = PolyClawAgent(
        llm_provider=provider,
        config=PolyClawConfig(
            use_docker=False,
            verbose=False,
            intent="execution",
            max_iterations=3,
        ),
    )

    result = agent.run("Verifica che pipeline fallita non riporti exit code 0")

    assert "verificato" in result.lower()
    assert any("[exit code: 127]" in entry for entry in agent._history)


def test_polyclaw_docker_runtime_uses_run_exec_stop(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    docker_path = "/usr/bin/docker"
    monkeypatch.setattr(shutil, "which", lambda name: docker_path if name == "docker" else None)

    calls = []

    def fake_subprocess_run(cmd, **kwargs):
        calls.append(cmd)
        if len(cmd) >= 2 and cmd[1] == "run":
            return subprocess.CompletedProcess(cmd, 0, stdout="container-id\n", stderr="")
        if len(cmd) >= 2 and cmd[1] == "exec":
            return subprocess.CompletedProcess(cmd, 0, stdout="inside-docker\n", stderr="")
        if len(cmd) >= 2 and cmd[1] == "stop":
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    provider = ScriptedLLMProvider(
        [
            """```bash
echo "hello from docker runtime"
```
""",
            """```FINAL
Docker runtime path verified.
```""",
        ]
    )

    agent = PolyClawAgent(
        llm_provider=provider,
        config=PolyClawConfig(
            use_docker=True,
            verbose=False,
            intent="execution",
            max_iterations=3,
            docker_image="python:3.11-slim",
        ),
    )

    result = agent.run("Verifica path runtime docker")

    assert "verified" in result.lower()
    assert any(len(cmd) >= 2 and cmd[1] == "run" for cmd in calls)
    assert any(len(cmd) >= 2 and cmd[1] == "exec" for cmd in calls)
    assert any(len(cmd) >= 2 and cmd[1] == "stop" for cmd in calls)


def _docker_is_usable() -> bool:
    docker_bin = shutil.which("docker")
    if not docker_bin:
        return False
    try:
        result = subprocess.run(
            [docker_bin, "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


@pytest.mark.skipif(
    os.getenv("POLYMCP_RUN_DOCKER_TESTS") != "1",
    reason="Set POLYMCP_RUN_DOCKER_TESTS=1 to run real Docker integration tests.",
)
def test_polyclaw_real_docker_integration(tmp_path, monkeypatch):
    if not _docker_is_usable():
        pytest.skip("Docker is not available/usable on this machine.")

    monkeypatch.chdir(tmp_path)

    provider = ScriptedLLMProvider(
        [
            """```bash
mkdir -p integration-output
printf 'DOCKER_E2E_OK\n' > integration-output/result.txt
cat integration-output/result.txt
```
""",
            """```FINAL
E2E docker test completed.
```""",
        ]
    )

    agent = PolyClawAgent(
        llm_provider=provider,
        config=PolyClawConfig(
            use_docker=True,
            docker_enable_network=False,
            docker_image="python:3.11-slim",
            verbose=False,
            intent="execution",
            max_iterations=4,
            command_timeout=120.0,
        ),
    )

    result = agent.run("Esegui test e2e docker")

    output_file = Path(tmp_path) / "integration-output" / "result.txt"
    assert output_file.exists()
    assert output_file.read_text(encoding="utf-8").strip() == "DOCKER_E2E_OK"
    assert "completed" in result.lower()
