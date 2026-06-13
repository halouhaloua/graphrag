from loguru import logger
import os
import tempfile
from typing import Any, Dict

import aiohttp
import arxiv
from PyPDF2 import PdfReader

from ai_workflow.nodes.base import BaseNode, NodeContext
from ai_workflow.nodes.registry import register_node




@register_node(
    "arxiv_search",
    metadata={
        "name": "Arxiv论文搜索",
        "description": "搜索Arxiv学术论文库，返回最相关的论文信息",
        "params": {
            "query": {
                "type": "str",
                "required": True,
                "description": "搜索关键词（英文）",
            },
            "max_results": {"type": "int", "default": 5, "description": "最大返回数量"},
            "extract_fulltext": {
                "type": "bool",
                "default": False,
                "description": "是否提取PDF全文",
            },
        },
        "output": {"results": "论文列表", "count": "数量", "success": "是否成功"},
    },
)
class ArxivSearchNode(BaseNode):
    """Arxiv学术论文搜索节点"""

    async def execute(
        self, params: Dict[str, Any], context: NodeContext
    ) -> Dict[str, Any]:
        query = params.get("query")
        if not query:
            return {
                "success": False,
                "error": "Missing required parameter: query",
                "results": [],
            }

        max_results = int(params.get("max_results", 5))
        extract_fulltext = bool(params.get("extract_fulltext", False))

        try:
            client = arxiv.Client()
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.Relevance,
            )
            results = []
            for paper in client.results(search):
                paper_info = {
                    "title": paper.title,
                    "authors": [a.name for a in paper.authors],
                    "summary": paper.summary,
                    "published": paper.published.strftime("%Y-%m-%d"),
                    "pdf_url": paper.pdf_url,
                    "entry_id": paper.entry_id,
                    "primary_category": paper.primary_category,
                    "content": "",
                }
                if extract_fulltext and paper.pdf_url:
                    paper_info["content"] = await self._download_pdf_text(paper.pdf_url)
                results.append(paper_info)

            return {"success": True, "results": results, "count": len(results)}

        except Exception as e:
            logger.error(f"Arxiv搜索失败: {e}")
            return {"success": False, "error": str(e), "results": []}

    async def _download_pdf_text(self, pdf_url: str) -> str:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    pdf_url, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        return f"下载失败, status: {resp.status}"
                    content = await resp.read()

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(content)
                tmp_path = f.name

            try:
                reader = PdfReader(tmp_path)
                texts = [page.extract_text() for page in reader.pages]
                return "\n".join(texts)
            except Exception as e:
                logger.error(f"PDF解析失败: {e}")
                return f"PDF解析失败: {e}"
            finally:
                os.unlink(tmp_path)
        except Exception as e:
            logger.error(f"PDF下载失败: {e}")
            return f"PDF下载失败: {e}"
