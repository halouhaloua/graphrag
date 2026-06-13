import aiohttp
from typing import Any, Dict

from ai_workflow.nodes.base import BaseNode, NodeContext
from ai_workflow.nodes.registry import register_node


@register_node(
    "api_call",
    metadata={
        "name": "API调用",
        "description": "通用REST API调用，支持Bearer Token认证",
        "params": {
            "url": {"type": "str", "required": True, "description": "API地址"},
            "method": {
                "type": "str",
                "required": True,
                "description": "HTTP方法(GET/POST/PUT/DELETE)",
            },
            "headers": {"type": "dict", "default": {}, "description": "请求头"},
            "body": {"type": "dict", "default": None, "description": "请求体"},
            "bearer_token": {
                "type": "str",
                "default": None,
                "description": "Bearer Token",
            },
        },
        "output": {"data": "响应数据", "status": "HTTP状态码", "success": "是否成功"},
    },
)
class ApiCallNode(BaseNode):
    """通用REST API调用节点，支持Bearer Token认证"""

    async def execute(
        self, params: Dict[str, Any], context: NodeContext
    ) -> Dict[str, Any]:
        url = params.get("url")
        if not url:
            raise ValueError("url参数不能为空")
        method = params.get("method", "GET").upper()
        headers = params.get("headers", {})
        body = params.get("body")
        bearer_token = params.get("bearer_token")

        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=method, url=url, headers=headers, json=body if body else None
                ) as response:
                    data = await response.json()
                    return {
                        "result": data,
                        "status": response.status,
                        "success": response.status < 400,
                        "headers": dict(response.headers),
                    }
        except Exception as e:
            return {"result": None, "status": None, "success": False, "error": str(e)}
