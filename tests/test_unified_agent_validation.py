import pytest

from polymcp.polyagent.llm_providers import LLMProvider
from polymcp.polyagent.unified_agent import AgentResult, UnifiedPolyAgent


class DummyProvider(LLMProvider):
    def generate(self, prompt: str, **kwargs) -> str:  # pragma: no cover - patched in tests
        return '{"achieved": false, "confidence": 0.0, "reason": "stub"}'


@pytest.mark.asyncio
async def test_conservative_validation_stops_on_equal_threshold(monkeypatch):
    agent = UnifiedPolyAgent(
        llm_provider=DummyProvider(),
        use_planner=False,
        use_validator=True,
        validation_mode="conservative",
        goal_achievement_threshold=0.85,
        skills_sh_enabled=False,
        enable_rate_limiting=False,
        enable_health_checks=False,
        verbose=False,
    )

    async def fake_get_all_tools():
        return [
            {
                "name": "dummy_tool",
                "description": "dummy",
                "input_schema": {"type": "object", "properties": {}},
                "_server_url": "dummy://server",
                "_server_type": "http",
            }
        ]

    def fake_select_tool_with_constraints(*args, **kwargs):
        return {
            "name": "dummy_tool",
            "description": "dummy",
            "input_schema": {"type": "object", "properties": {}},
            "_server_url": "dummy://server",
            "_server_type": "http",
            "_parameters": {},
        }

    async def fake_execute_tool_with_retry(tool):
        return AgentResult(status="success", result={"text": "done"})

    async def fake_validate_goal_achieved(user_message, action_history):
        # Equality case that previously caused loops because code used ">"
        return True, 0.95, "goal completed"

    def fake_generate_final_response(user_message, action_history):
        return "ok"

    monkeypatch.setattr(agent, "_get_all_tools", fake_get_all_tools)
    monkeypatch.setattr(agent, "_select_tool_with_constraints", fake_select_tool_with_constraints)
    monkeypatch.setattr(agent, "_execute_tool_with_retry", fake_execute_tool_with_retry)
    monkeypatch.setattr(agent, "_validate_goal_achieved", fake_validate_goal_achieved)
    monkeypatch.setattr(agent, "_generate_final_response", fake_generate_final_response)

    response = await agent.run_async("Do the task", max_steps=5)

    assert response == "ok"
    assert agent._persistent_history is not None
    # Should stop after one successful action + one validation check.
    assert len(agent._persistent_history) == 1


def test_result_preview_extracts_text_from_content():
    agent = UnifiedPolyAgent(
        llm_provider=DummyProvider(),
        use_planner=False,
        use_validator=False,
        skills_sh_enabled=False,
        enable_rate_limiting=False,
        enable_health_checks=False,
        verbose=False,
    )

    preview = agent._result_preview_text(
        {
            "status": "success",
            "content": [
                {"type": "text", "text": "Example Domain"},
                {"type": "text", "text": "Secondary detail"},
            ],
        }
    )

    assert "Example Domain" in preview


def test_final_response_appends_key_outputs_when_response_not_grounded(monkeypatch):
    agent = UnifiedPolyAgent(
        llm_provider=DummyProvider(),
        use_planner=False,
        use_validator=False,
        skills_sh_enabled=False,
        enable_rate_limiting=False,
        enable_health_checks=False,
        verbose=False,
    )

    action_history = [
        {
            "step": 1,
            "tool": "browser_navigate",
            "result": AgentResult(
                status="success",
                result={"content": [{"type": "text", "text": "Example Domain"}]},
            ),
        }
    ]

    monkeypatch.setattr(
        agent.llm_provider,
        "generate",
        lambda prompt, **kwargs: "I navigated, but I don't have the page title at the moment.",
    )

    response = agent._generate_final_response(
        "Navigate to example.com and get the page title",
        action_history,
    )

    assert "Key outputs:" in response
    assert "Example Domain" in response
