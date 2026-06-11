"""工作流节点单元测试

测试策略：
- 每个节点验证 @register_node 生效
- 验证 execute 签名包含 (params, context)
- 验证缺失必填参数时正确处理
- 验证 NodeContext 可注入
"""

from dataclasses import dataclass

import pytest

from ai_workflow.nodes.base import BaseNode, NodeContext
from ai_workflow.nodes.registry import NodeRegistry


@dataclass
class FakeSettings:
    LLM_MODEL: str = "test-model"
    LLM_BASE_URL: str = "https://test.api.com"
    LLM_API_KEY: str = "test-key"


@dataclass
class FakeLogger:
    def info(self, *a, **kw):
        pass

    def error(self, *a, **kw):
        pass

    def warning(self, *a, **kw):
        pass


@pytest.fixture
def ctx():
    return NodeContext(
        db=None,
        settings=FakeSettings(),
        logger=FakeLogger(),
        node_id="test-node",
        instance_id="test-instance",
    )


class TestNodeRegistration:
    """所有已注册节点均可通过 NodeRegistry 获取"""

    REGISTERED_TYPES = [
        "api_call",
        "chat",
        "python_execute",
        "arxiv_search",
        "weather_forecast",
        "serper_search",
        "browser_agent",
        "web_crawler",
    ]

    def test_all_nodes_registered(self):
        for t in self.REGISTERED_TYPES:
            cls = NodeRegistry.get(t)
            assert cls is not None, f"节点类型 {t} 未注册"
            assert issubclass(cls, BaseNode)

    def test_node_metadata_available(self):
        for t in self.REGISTERED_TYPES:
            meta = NodeRegistry.get_metadata(t)
            assert meta is not None, f"节点 {t} 缺少 metadata"
            assert "name" in meta
            assert "description" in meta
            assert "params" in meta
            assert "output" in meta


class TestApiCallNode:
    @pytest.mark.asyncio
    async def test_signature(self, ctx):
        node = NodeRegistry.get("api_call")()
        assert hasattr(node, "execute")

    @pytest.mark.asyncio
    async def test_missing_url_raises(self, ctx):
        node = NodeRegistry.get("api_call")()
        with pytest.raises(ValueError, match="url"):
            await node.execute({"method": "GET"}, ctx)


class TestChatNode:
    @pytest.mark.asyncio
    async def test_signature(self, ctx):
        node = NodeRegistry.get("chat")()
        assert hasattr(node, "execute")

    @pytest.mark.asyncio
    async def test_empty_question_returns_error(self, ctx):
        node = NodeRegistry.get("chat")()
        result = await node.execute({"user_question": ""}, ctx)
        assert "error" in result

    def test_chat_metadata_has_tools_param(self):
        meta = NodeRegistry.get_metadata("chat")
        assert meta is not None
        params = meta.get("params", {})
        assert "tools" in params
        assert params["tools"]["type"] == "list"
        assert "max_tool_rounds" in params
        assert params["max_tool_rounds"]["default"] == 10

    def test_chat_no_tools_returns_same_metadata(self):
        """验证 tools=[] 时 metadata 仍然兼容原有参数"""
        meta = NodeRegistry.get_metadata("chat")
        assert "user_question" in meta.get("params", {})
        assert "system_prompt" in meta.get("params", {})
        assert "temperature" in meta.get("params", {})


class TestPythonExecuteNode:
    @pytest.mark.asyncio
    async def test_signature(self, ctx):
        node = NodeRegistry.get("python_execute")()
        assert hasattr(node, "execute")

    @pytest.mark.asyncio
    async def test_missing_code_raises(self, ctx):
        node = NodeRegistry.get("python_execute")()
        with pytest.raises(ValueError, match="code"):
            await node.execute({"language": "python"}, ctx)

    @pytest.mark.asyncio
    async def test_invalid_language_raises(self, ctx):
        node = NodeRegistry.get("python_execute")()
        with pytest.raises(ValueError, match="language"):
            await node.execute({"code": "print(1)", "language": "java"}, ctx)


class TestArxivSearchNode:
    @pytest.mark.asyncio
    async def test_signature(self, ctx):
        node = NodeRegistry.get("arxiv_search")()
        assert hasattr(node, "execute")

    @pytest.mark.asyncio
    async def test_missing_query_returns_error(self, ctx):
        node = NodeRegistry.get("arxiv_search")()
        result = await node.execute({"max_results": 3}, ctx)
        assert result["success"] is False


class TestWeatherForecastNode:
    @pytest.mark.asyncio
    async def test_signature(self, ctx):
        node = NodeRegistry.get("weather_forecast")()
        assert hasattr(node, "execute")

    @pytest.mark.asyncio
    async def test_missing_coords_raises(self, ctx):
        node = NodeRegistry.get("weather_forecast")()
        with pytest.raises(ValueError, match="latitude"):
            await node.execute({}, ctx)


class TestSerperSearchNode:
    @pytest.mark.asyncio
    async def test_signature(self, ctx):
        node = NodeRegistry.get("serper_search")()
        assert hasattr(node, "execute")

    @pytest.mark.asyncio
    async def test_missing_query_raises(self, ctx):
        node = NodeRegistry.get("serper_search")()
        with pytest.raises(ValueError, match="query"):
            await node.execute({"max_results": 5}, ctx)


class TestBrowserAgentNode:
    @pytest.mark.asyncio
    async def test_signature(self, ctx):
        node = NodeRegistry.get("browser_agent")()
        assert hasattr(node, "execute")

    @pytest.mark.asyncio
    async def test_missing_task_raises(self, ctx):
        node = NodeRegistry.get("browser_agent")()
        with pytest.raises(ValueError, match="task"):
            await node.execute({}, ctx)

    def test_has_close_method(self):
        node = NodeRegistry.get("browser_agent")()
        assert hasattr(node, "close")


class TestWebCrawlerNode:
    @pytest.mark.asyncio
    async def test_signature(self, ctx):
        node = NodeRegistry.get("web_crawler")()
        assert hasattr(node, "execute")

    @pytest.mark.asyncio
    async def test_missing_url_raises(self, ctx):
        node = NodeRegistry.get("web_crawler")()
        with pytest.raises(ValueError, match="url"):
            await node.execute({}, ctx)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
