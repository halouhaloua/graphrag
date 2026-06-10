import json
import logging
import os
from typing import Any, Dict

import aiohttp

from ai_workflow.nodes.base import BaseNode, NodeContext
from ai_workflow.nodes.registry import register_node

logger = logging.getLogger(__name__)


@register_node(
    "weather_forecast",
    metadata={
        "name": "天气预报",
        "description": "通过彩云天气API获取经纬度对应的天气信息",
        "params": {
            "latitude": {"type": "float", "required": True, "description": "纬度"},
            "longitude": {"type": "float", "required": True, "description": "经度"},
        },
        "output": {"data": "天气数据", "success": "是否成功"},
    },
)
class WeatherForecastNode(BaseNode):
    """天气预报节点 - 使用彩云天气API获取天气信息"""

    async def execute(
        self, params: Dict[str, Any], context: NodeContext
    ) -> Dict[str, Any]:
        latitude = float(params.get("latitude", 0))
        longitude = float(params.get("longitude", 0))
        if not latitude or not longitude:
            raise ValueError("latitude和longitude参数不能为空")

        api_version = params.get("version", os.getenv("caiyun_api_version", "2.6"))
        token = params.get("token", os.getenv("caiyun_token", ""))

        if not token:
            return {"success": False, "error": "未配置彩云天气API Token", "data": None}

        try:
            async with aiohttp.ClientSession() as session:
                realtime_url = (
                    f"https://api.caiyunapp.com/v{api_version}/{token}/"
                    f"{longitude},{latitude}/realtime"
                )
                async with session.get(realtime_url) as resp:
                    resp.raise_for_status()
                    realtime = (await resp.json())["result"]["realtime"]

                daily_url = (
                    f"https://api.caiyunapp.com/v{api_version}/{token}/"
                    f"{longitude},{latitude}/daily"
                )
                async with session.get(daily_url, params={"dailysteps": "3"}) as resp:
                    resp.raise_for_status()
                    daily = (await resp.json())["result"]["daily"]

            weather_data = {"realtime": realtime, "daily": daily}
            return {
                "success": True,
                "data": weather_data,
                "result": json.dumps(weather_data, ensure_ascii=False),
            }

        except aiohttp.ClientError as e:
            logger.error(f"天气API请求失败: {e}")
            return {"success": False, "error": f"请求失败: {e}", "data": None}
        except Exception as e:
            logger.error(f"获取天气失败: {e}")
            return {"success": False, "error": str(e), "data": None}
