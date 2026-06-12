import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

import aiohttp
from PyPDF2 import PdfReader

from ai_workflow.nodes.base import BaseNode, NodeContext
from ai_workflow.nodes.registry import register_node
from utils.rate_limiter import AsyncRateLimiter
from utils.redis import RedisClient

logger = logging.getLogger(__name__)


@register_node(
    "web_crawler",
    metadata={
        "name": "网络爬虫",
        "description": "根据URL爬取网页正文内容（支持HTML和PDF）",
        "params": {
            "url": {
                "type": "str",
                "required": True,
                "description": "需要抓取的网页链接",
            },
        },
        "output": {"content": "提取的正文内容", "success": "是否成功"},
    },
)
class SerperScrapeNode(BaseNode):
    """网络爬虫节点

    通过 Serper API 获取网页正文（markdown格式），
    支持 PDF 文件解析和 Redis 缓存。
    """

    _rate_limiter = AsyncRateLimiter(max_requests_per_minute=5)

    async def execute(
        self, params: Dict[str, Any], context: NodeContext
    ) -> Dict[str, Any]:
        url = str(params.get("url", "")).strip()
        if not url:
            raise ValueError("url参数不能为空")

        cache_key = f"crawler:cache:{url}"

        redis_client = await RedisClient.get_client()
        cached = await redis_client.get(cache_key)
        if cached is not None:
            logger.info(f"爬虫缓存命中: {url}")
            return {"success": True, "content": cached}

        try:
            if url.lower().endswith(".pdf"):
                text = await self._download_pdf(url)
            else:
                text = await self._scrape_webpage(url)

            if text:
                ttl = int(os.getenv("WEB_CRAWLER_CACHE_TTL", "3600"))
                await redis_client.set(cache_key, text, ex=ttl)

            return {"success": True, "content": text or ""}

        except aiohttp.ClientError as e:
            logger.error(f"爬取请求失败: {url}, {e}")
            return {"success": False, "error": f"请求失败: {e}"}
        except Exception as e:
            logger.error(f"爬取失败: {url}, {e}")
            return {"success": False, "error": str(e)}

    async def _scrape_webpage(self, url: str) -> str:
        api_key = os.getenv("SERPER_CRAWL_API_KEY", "")
        if not api_key:
            raise ValueError("未设置SERPER_CRAWL_API_KEY环境变量")

        await self._rate_limiter.acquire()

        headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
        data = {"url": url, "includeMarkdown": True}

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=120)
        ) as session:
            async with session.post(
                "https://scrape.serper.dev", headers=headers, json=data
            ) as response:
                response.raise_for_status()
                result = await response.json()
                return result.get("markdown", "")

    async def _download_pdf(self, url: str) -> str:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=3600)
        ) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                content = await response.read()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "temp.pdf"
            with open(tmp_path, "wb") as f:
                f.write(content)
            reader = PdfReader(tmp_path)
            texts = [page.extract_text() for page in reader.pages]
            return "\n".join(texts)
