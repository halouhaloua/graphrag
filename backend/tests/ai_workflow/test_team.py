"""团队模块单元测试

测试策略：
- TeamConfig schema 校验
- TeamExecutor 的 action 解析逻辑
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
from ai_workflow.team.service import TeamExecutor


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


class TestTeamExecutor:
    """TeamExecutor action 解析测试"""

    def test_parse_handoff(self):
        text = """
        <action>
          <handoff>
            <target_role>RESEARCHER</target_role>
            <context>已完成初步分析</context>
          </handoff>
        </action>
        """
        action = TeamExecutor._parse_action(text, ["handoff", "serper_search"])
        assert action["type"] == "handoff"
        assert action["target_role"] == "RESEARCHER"
        assert action["context"] == "已完成初步分析"

    def test_parse_final_answer(self):
        text = """
        <action>
          <final_answer>
            <result>最终答案</result>
          </final_answer>
        </action>
        """
        action = TeamExecutor._parse_action(text, ["handoff", "final_answer"])
        assert action["type"] == "final_answer"
        assert action["result"] == "最终答案"

    def test_parse_tool_call(self):
        text = """
        <action>
          <serper_search>
            <query>人工智能最新发展</query>
            <max_results>5</max_results>
          </serper_search>
        </action>
        """
        action = TeamExecutor._parse_action(text, ["serper_search"])
        assert action["type"] == "tool_call"
        assert action["tool_name"] == "serper_search"
        assert action["tool_args"]["query"] == "人工智能最新发展"
        assert action["tool_args"]["max_results"] == "5"

    def test_parse_unknown_action(self):
        text = "这是一个普通文本，没有 XML 标签"
        action = TeamExecutor._parse_action(text, ["handoff"])
        assert action["type"] == "unknown"

    def test_parse_xml_args(self):
        xml = "<query>测试</query><count>10</count>"
        args = TeamExecutor._parse_xml_args(xml)
        assert args["query"] == "测试"
        assert args["count"] == "10"


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
