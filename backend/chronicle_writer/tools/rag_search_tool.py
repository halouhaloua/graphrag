import json

from agentscope.tool import ToolBase, ToolChunk
from agentscope.permission import (
    PermissionContext,
    PermissionDecision,
    PermissionBehavior,
)
from agentscope.message import TextBlock
from loguru import logger

from chronicle_writer.tools.rag_recall import ircot_recall


class RAGSearchTool(ToolBase):
    """知识图谱搜索工具 — 在用户选定的知识库中搜索事实"""

    name = "RAGSearch"
    description = (
        "在选定的知识图谱知识库中搜索事实、实体关系和数据。"
        "检索范围由用户在前端选择知识库时确定，调用时无需指定。"
        "返回带来源和置信度的三元组结果。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询，如'某县2020年人口'或'简述该地区建置沿革'",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    }
    is_concurrency_safe = True
    is_read_only = True

    async def check_permissions(
        self,
        tool_input: dict,
        context: PermissionContext,
    ) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="RAG search is read-only.",
        )

    async def __call__(self, query: str) -> ToolChunk:
        try:
            result = await ircot_recall(query)
            formatted = self._format_for_llm(result)
            return ToolChunk(content=[TextBlock(text=formatted)])
        except Exception as e:
            logger.error(f"RAGSearch failed: {e}")
            return ToolChunk(content=[TextBlock(text=json.dumps({"error": str(e)}))])

    def _format_for_llm(self, result: dict) -> str:
        """将结构化检索结果格式化为 LLM 友好的文本"""
        parts = []

        triples = result.get("triples", [])
        chunks = result.get("chunk_contents", [])
        sub_questions = result.get("sub_questions", [])

        parts.append(f"共检索到 {result.get('file_count', 0)} 个文件中的知识。")

        if sub_questions:
            parts.append("\n分析维度：")
            for sq in sub_questions:
                parts.append(f"- {sq.get('sub-question', '')}")

        if triples:
            parts.append(f"\n相关事实（共 {len(triples)} 条）：")
            for t in triples[:30]:
                parts.append(f"  {t}")

        if chunks:
            parts.append(f"\n相关原文段落（共 {len(chunks)} 段）：")
            for c in chunks[:5]:
                text = c[:300] + "..." if len(c) > 300 else c
                parts.append(f"  {text}")

        return "\n".join(parts)


class VerifyFactTool(ToolBase):
    """事实验证工具 — 验证陈述是否与知识图谱中的事实一致"""

    name = "VerifyFact"
    description = (
        "验证一个陈述是否与知识图谱中的事实一致，返回置信度和矛盾证据。"
        "自动在用户选定的知识库范围内搜索。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "claim": {
                "type": "string",
                "description": "待验证的陈述，如'该县2020年人口约50万'",
            },
            "threshold": {
                "type": "number",
                "description": "置信度阈值，低于此值标记为可疑",
                "default": 0.7,
            },
        },
        "required": ["claim"],
        "additionalProperties": False,
    }
    is_concurrency_safe = True
    is_read_only = True

    async def check_permissions(
        self,
        tool_input: dict,
        context: PermissionContext,
    ) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="Fact verification is read-only.",
        )

    async def __call__(self, claim: str, threshold: float = 0.7) -> ToolChunk:
        try:
            result = await self._verify(claim, threshold)
            return ToolChunk(
                content=[TextBlock(text=json.dumps(result, ensure_ascii=False))]
            )
        except Exception as e:
            logger.error(f"VerifyFact failed: {e}")
            return ToolChunk(content=[TextBlock(text=json.dumps({"error": str(e)}))])

    async def _verify(self, claim: str, threshold: float) -> dict:
        from rag.utils.call_llm_api import LLMCompletionCall

        llm = LLMCompletionCall()

        extraction_prompt = (
            f"从以下陈述中提取(主语, 谓语, 宾语)三元组，以JSON数组格式返回。\n"
            f"陈述：{claim}\n"
            f'格式: [{{"subject": "...", "predicate": "...", "object": "..."}}]'
        )
        try:
            extraction = llm.call_api(extraction_prompt)
            triples = json.loads(extraction)
        except Exception:
            triples = [
                {"subject": claim[:50], "predicate": "描述", "object": claim[-50:]}
            ]

        evidence = []
        contradictions = []
        for triple in triples:
            search_query = (
                f"{triple['subject']} {triple['predicate']} {triple['object']}"
            )
            recall = await ircot_recall(search_query)
            matched = recall.get("triples", [])

            if matched:
                evidence.append(
                    {
                        "triple": triple,
                        "matches": matched[:3],
                        "match_count": len(matched),
                    }
                )
            else:
                contradictions.append(
                    {
                        "triple": triple,
                        "reason": "在知识图谱中未找到匹配的事实",
                    }
                )

        confidence = len(evidence) / max(len(triples), 1)
        return {
            "verified": confidence >= threshold,
            "confidence": round(confidence, 2),
            "evidence": evidence,
            "contradictions": contradictions,
            "suggestions": "建议查阅最新统计年鉴" if contradictions else "",
        }
