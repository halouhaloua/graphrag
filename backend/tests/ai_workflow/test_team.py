"""团队模块单元测试

测试策略：
- TeamConfig schema 校验
- HandoffTool / FinalAnswerTool 的 schema 正确性
- NodeToolAdapter 适配器正确映射节点参数
- YAML 导入解析
"""

import yaml
import pytest

from ai_workflow.team.schema import (
    TeamConfigCreate,
    TeamRoleSchema,
    TeamConfigOut,
    TeamYamlImport,
)
from ai_workflow.team.team_tools import HandoffTool, FinalAnswerTool
from ai_workflow.team.tool_adapter import NodeToolAdapter
from ai_workflow.nodes.loader import load_all_nodes, reset_loaded
from ai_workflow.nodes.registry import NodeRegistry
from app.config import settings


SAMPLE_YAML = """
team_rules: "你们是一个出色的研究团队"
start_role: "COORDINATOR"
roles:
  COORDINATOR:
    tools: ["handoff", "final_answer"]
    agent_description: "协调者"
    model_name: "deepseek-chat"
    max_iterations: 25
    termination_conditions:
      - type: "ToolTerminationCondition"
        tool_names: ["final_answer"]
  RESEARCHER:
    tools: ["serper_search", "web_crawler", "handoff", "final_answer"]
    agent_description: "研究员"
    model_name: "deepseek-chat"
    max_iterations: 25
"""


class TestTeamConfigSchema:
    """团队配置 schema 校验"""

    def test_valid_create(self):
        data = TeamConfigCreate(
            name="研究团队",
            team_rules="你们是一个出色的研究团队",
            start_role="COORDINATOR",
            roles={
                "COORDINATOR": TeamRoleSchema(
                    tools=["handoff", "final_answer"],
                    agent_description="协调者",
                ),
                "RESEARCHER": TeamRoleSchema(
                    tools=["serper_search", "web_crawler", "handoff"],
                    agent_description="研究员",
                ),
            },
        )
        assert data.name == "研究团队"
        assert data.start_role == "COORDINATOR"
        assert "RESEARCHER" in data.roles

    def test_role_defaults(self):
        role = TeamRoleSchema(tools=["handoff"])
        assert role.max_iterations == 25
        assert role.model_name == "deepseek-chat"

    def test_out_parse_json_roles(self):
        raw = {
            "id": "test123",
            "name": "团队",
            "team_rules": "规则",
            "start_role": "COORDINATOR",
            "roles": '{"COORDINATOR": {"tools": ["handoff"], "agent_description": "协调者", "model_name": "deepseek-chat", "max_iterations": 25, "termination_conditions": []}}',
            "is_active": True,
            "sort": 0,
            "is_deleted": False,
        }
        out = TeamConfigOut.model_validate(raw)
        assert "COORDINATOR" in out.roles
        assert out.roles["COORDINATOR"].tools == ["handoff"]


class TestTeamTools:
    """HandoffTool / FinalAnswerTool schema 测试"""

    def test_handoff_tool_has_schema(self):
        tool = HandoffTool()
        assert tool.name == "handoff"
        assert "target_role" in tool.input_schema.get("properties", {})
        assert "context" in tool.input_schema.get("properties", {})
        assert tool.input_schema.get("required") == ["target_role", "context"]

    def test_final_answer_tool_has_schema(self):
        tool = FinalAnswerTool()
        assert tool.name == "final_answer"
        assert "result" in tool.input_schema.get("properties", {})
        assert tool.input_schema.get("required") == ["result"]

    def test_handoff_call_returns_tool_chunk(self):
        tool = HandoffTool()
        import pytest_asyncio  # noqa: F401

        async def _run():
            chunk = await tool(target_role="RESEARCHER", context="完成分析")
            text = chunk.content[0].text if chunk.content else ""
            assert "RESEARCHER" in text
        import asyncio
        asyncio.run(_run())

    def test_final_answer_call_returns_tool_chunk(self):
        tool = FinalAnswerTool()

        async def _run():
            chunk = await tool(result="最终答案")
            assert chunk.content[0].text == "最终答案"
        import asyncio
        asyncio.run(_run())


class TestNodeToolAdapter:
    """NodeToolAdapter 适配器测试"""

    @pytest.fixture(autouse=True)
    def setup_nodes(self):
        reset_loaded()
        load_all_nodes()
        yield
        reset_loaded()

    def test_adapter_serper_search_schema(self):
        adapter = NodeToolAdapter("serper_search", settings)
        assert adapter.name == "serper_search"
        props = adapter.input_schema.get("properties", {})
        assert "query" in props
        assert props["query"]["type"] == "string"
        assert adapter.input_schema.get("required") == ["query"]

    def test_adapter_web_crawler_schema(self):
        adapter = NodeToolAdapter("web_crawler", settings)
        assert adapter.name == "web_crawler"
        props = adapter.input_schema.get("properties", {})
        assert "url" in props
        assert props["url"]["type"] == "string"

    def test_adapter_weather_forecast_schema(self):
        adapter = NodeToolAdapter("weather_forecast", settings)
        props = adapter.input_schema.get("properties", {})
        assert "latitude" in props
        assert props["latitude"]["type"] == "number"
        assert "longitude" in props
        assert props["longitude"]["type"] == "number"

    def test_adapter_unknown_node_type(self):
        adapter = NodeToolAdapter("nonexistent_node", settings)
        assert adapter.name == "nonexistent_node"
        # unknown type should have empty properties
        assert adapter.input_schema.get("properties", {}) == {}

    def test_adapter_has_description(self):
        adapter = NodeToolAdapter("chat", settings)
        assert adapter.description


class TestYamlImport:
    """YAML 导入解析测试"""

    def test_parse_sample_yaml(self):
        parsed = yaml.safe_load(SAMPLE_YAML)
        assert parsed["team_rules"] == "你们是一个出色的研究团队"
        assert parsed["start_role"] == "COORDINATOR"
        assert "COORDINATOR" in parsed["roles"]
        assert "RESEARCHER" in parsed["roles"]
        assert "serper_search" in parsed["roles"]["RESEARCHER"]["tools"]

    def test_team_yaml_import_schema(self):
        data = TeamYamlImport(yaml_content=SAMPLE_YAML, name="测试团队")
        assert data.name == "测试团队"
        assert "roles" in data.yaml_content
