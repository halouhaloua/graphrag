"""RAG 知识库问答节点

基于已构建的知识图谱进行检索增强问答（RAG），支持 IRCoT 迭代检索模式。
接收上游节点输出作为问题，支持知识库和文件选择。

使用前置条件：知识库文件必须已经构建过知识图谱（``has_graph=True``）。
"""

import json

import re
from typing import Any, Dict, Optional

from sqlalchemy import select

from ai_workflow.nodes.base import BaseNode, NodeContext
from ai_workflow.nodes.registry import register_node
from ai_workflow.workflow.events import WorkflowEventType

from loguru import logger

# IRCoT 答案标记
_ANSWER_MARKER = "So the answer is:"
_QUERY_MARKER = "The new query is:"


@register_node(
    "rag_query",
    metadata={
        "name": "知识库问答",
        "description": "基于已构建图谱的知识库进行检索增强问答（RAG），支持 IRCoT 模式",
        "params": {
            "kb_id": {
                "type": "str",
                "required": True,
                "description": "知识库ID",
            },
            "file_id": {
                "type": "str",
                "default": "",
                "description": "文件ID（可选，不填时自动选择有图谱的文件）",
            },
            "question": {
                "type": "str",
                "default": "${_input.message}",
                "description": "用户问题（支持 ${node.key} 引用上游输出）",
            },
            "enable_ircot": {
                "type": "bool",
                "default": False,
                "description": "启用 IRCoT（迭代检索链式推理）模式",
            },
            "top_k": {
                "type": "int",
                "default": 10,
                "description": "检索返回的 top-k 三元组数量",
            },
        },
        "output": {
            "result": "AI 回答文本",
            "sources": "引用来源列表（三元组 + 文本块）",
            "ircot_steps": "IRCoT 迭代步数（启用 IRCoT 时）",
            "success": "是否成功",
        },
    },
)
class RagQueryNode(BaseNode):
    """知识库问答节点

    接收来自上游节点的输出进行 RAG 问答。工作流编排示例::

        start → db_query(查询配置) → rag_query → _end

    支持:
    - 指定知识库和文件
    - 自动选择有图谱的文件
    - IRCoT 迭代检索模式
    - SSE 流式输出令牌
    """

    async def execute(
        self, params: Dict[str, Any], context: NodeContext
    ) -> Dict[str, Any]:
        kb_id = str(params.get("kb_id", "")).strip()
        file_id = str(params.get("file_id", "")).strip()
        question = str(params.get("question", "")).strip()
        enable_ircot = bool(params.get("enable_ircot", False))
        top_k = int(params.get("top_k", 10))

        if not kb_id:
            raise ValueError("kb_id 参数不能为空")
        if not question:
            raise ValueError("question 参数不能为空")

        db = context.db
        stream_queue = context.stream_queue

        try:
            # ── 1. 查询知识库 ──────────────────────────────────────────
            from rag.kb_manager.model import KnowledgeBase, KnowledgeBaseFile

            kb = await db.get(KnowledgeBase, kb_id)
            if not kb or kb.is_deleted:
                return {
                    "result": "", "sources": [],
                    "success": False,
                    "error": f"知识库不存在: {kb_id}",
                }

            await self._push_token(stream_queue, context.node_id, "📚 加载知识库数据...\n")

            # ── 2. 获取图谱数据 ───────────────────────────────────────
            file_ids_kg = await self._resolve_file_and_graph(
                db, kb_id, file_id,
            )
            if not file_ids_kg:
                return file_ids_kg

            graph_data, chunks_data = file_ids_kg
            await self._push_token(stream_queue, context.node_id, "🧠 初始化检索引擎...\n")

            # ── 3. 初始化 RAG 检索引擎 ────────────────────────────────
            from rag.config.config_loader import get_config
            from rag.rag_models.retrieval.retrieval_core import (
                init_retrieval_state, build_retrieval_indices,
                process_retrieval_results,
            )
            from rag.rag_models.retrieval.agentic_decomposer import GraphQ
            from rag.rag_models.retrieval.prompt_builder import (
                build_prompt, generate_answer, generate_answer_stream,
            )

            config = get_config()
            dataset_name = f"kb_{kb_id}"

            state = init_retrieval_state(
                dataset=dataset_name, config=config,
                graph_data=graph_data, chunks_data=chunks_data,
                top_k_triple=top_k, top_k_chunk=top_k, recall_paths=2,
            )
            build_retrieval_indices(state)
            await self._push_token(stream_queue, context.node_id, "🔍 分析问题...\n")

            # ── 4. 问题分解 ────────────────────────────────────────────
            graphq = GraphQ(
                dataset_name=dataset_name, config=config,
                schema_data=self._load_schema(db, kb_id, file_id),
            )
            try:
                decomposition = graphq.decompose(question=question)
                sub_questions = decomposition.get("sub_questions", [question])
                involved_types = decomposition.get("involved_types", {})
                logger.info("RAG 问题分解为 %d 个子问题", len(sub_questions))
            except Exception as e:
                logger.warning("RAG 问题分解失败，使用原问题: %s", e)
                sub_questions = [question]
                involved_types = {}

            # ── 5. 检索 ────────────────────────────────────────────────
            await self._push_token(stream_queue, context.node_id, "📖 检索知识库...\n")

            all_triples: list[str] = []
            all_chunks: dict[str, str] = {}
            community_summaries: list[dict] = []
            all_triples_data: list[dict] = []

            for sq in sub_questions:
                try:
                    ret_results, _ = process_retrieval_results(
                        state=state, question=sq,
                        involved_types=involved_types, retrieval_type="micro",
                    )
                    all_triples.extend(ret_results.get("triples", []))
                    all_chunks.update(ret_results.get("chunk_contents", {}))
                    community_summaries.extend(
                        ret_results.get("community_summaries", [])
                    )
                    all_triples_data.extend(ret_results.get("triples_data", []))
                except Exception as e:
                    logger.warning("子问题检索失败 '%s': %s", sq, e)

            # 去重
            seen: set[str] = set()
            unique_triples = [t for t in all_triples if not (t in seen or seen.add(t))]

            # ── 6. 构建上下文字符串 ──────────────────────────────────
            context_parts: list[str] = []
            if unique_triples:
                context_parts.append("## 知识三元组\n" + "\n".join(unique_triples))
            if all_chunks:
                chunk_text = "\n\n".join(
                    f"[片段 {cid}]: {text}"
                    for cid, text in all_chunks.items() if text
                )
                if chunk_text:
                    context_parts.append("## 原文片段\n" + chunk_text)
            if community_summaries:
                summaries_text = "\n\n".join(
                    s.get("summary", "") for s in community_summaries if s.get("summary")
                )
                if summaries_text:
                    context_parts.append("## 社区摘要\n" + summaries_text)

            context = "\n\n".join(context_parts)

            prompt = build_prompt(
                config=config, dataset=dataset_name,
                question=question, sub_questions=sub_questions,
                context=context,
            )
            await self._push_token(stream_queue, context.node_id, "🤔 生成答案...\n")

            # ── 7. 生成答案 ────────────────────────────────────────────
            if enable_ircot:
                answer, ircot_steps = await self._ircot_generate(
                    state, config, dataset_name,
                    question, sub_questions, prompt, context,
                    stream_queue, context.node_id,
                )
            else:
                ircot_steps = 0
                answer = await self._stream_generate(
                    state.llm_stream_client, prompt,
                    stream_queue, context.node_id,
                )

            # ── 8. 构建结果 ────────────────────────────────────────────
            sources: list[dict] = [
                {"type": "triple", "content": t} for t in unique_triples[:20]
            ]
            for cid, text in list(all_chunks.items())[:10]:
                if text and len(text) > 10:
                    sources.append({"type": "chunk", "id": cid, "content": text[:200]})

            result: dict[str, Any] = {
                "result": answer,
                "sources": json.dumps(sources, ensure_ascii=False),
                "success": True,
            }
            if enable_ircot:
                result["ircot_steps"] = ircot_steps

            return result

        except Exception as e:
            logger.exception("RAG 知识库问答失败")
            return {
                "result": "", "sources": [],
                "success": False,
                "error": f"RAG 问答失败: {e}",
            }

    # ── 私有方法 ────────────────────────────────────────

    async def _resolve_file_and_graph(
        self, db, kb_id: str, file_id: str,
    ) -> Optional[tuple]:
        """解析文件ID并返回 (graph_data, chunks_data)"""
        from rag.kb_manager.model import KnowledgeBaseFile
        from rag.graph_manager.model import KnowledgeGraph

        target_file_id = file_id

        if not target_file_id:
            # 使用 merged 图或第一个有图谱的文件
            result = await db.execute(
                select(KnowledgeBaseFile).where(
                    KnowledgeBaseFile.kb_id == kb_id,
                    KnowledgeBaseFile.filename == "__kb_merged__",
                    KnowledgeBaseFile.is_deleted == False,  # noqa: E712
                )
            )
            merged = result.scalar_one_or_none()
            if merged:
                target_file_id = merged.id
            else:
                result = await db.execute(
                    select(KnowledgeBaseFile).where(
                        KnowledgeBaseFile.kb_id == kb_id,
                        KnowledgeBaseFile.has_graph == True,  # noqa: E712
                        KnowledgeBaseFile.is_deleted == False,  # noqa: E712
                    )
                )
                files = result.scalars().all()
                if not files:
                    return None
                target_file_id = files[0].id

        result = await db.execute(
            select(KnowledgeGraph).where(
                KnowledgeGraph.file_id == target_file_id,
            )
        )
        kg = result.scalar_one_or_none()
        if not kg or not kg.graph_data:
            return None
        return (kg.graph_data, kg.chunks_data)

    async def _load_schema(self, db, kb_id: str, file_id: str) -> Optional[Any]:
        """获取文件的 schema_json"""
        from rag.kb_manager.model import KnowledgeBaseFile

        if not file_id:
            result = await db.execute(
                select(KnowledgeBaseFile).where(
                    KnowledgeBaseFile.kb_id == kb_id,
                    KnowledgeBaseFile.has_graph == True,  # noqa: E712
                )
            )
            file = result.scalars().first()
            if not file:
                return None
            return file.schema_json

        file = await db.get(KnowledgeBaseFile, file_id)
        return file.schema_json if file else None

    async def _stream_generate(
        self, llm_stream_client, prompt: str,
        stream_queue, node_id: str,
    ) -> str:
        """流式生成答案，推送 token 到 SSE"""
        full_text = ""
        try:
            async for token in llm_stream_client.call_api_stream(prompt):
                if token:
                    full_text += token
                    await self._push_token(stream_queue, node_id, token)
        except Exception as e:
            error_msg = f"\n\n[生成错误: {e}]"
            full_text += error_msg
            await self._push_token(stream_queue, node_id, error_msg)
            logger.error("RAG 答案生成失败: %s", e)
        return full_text

    async def _ircot_generate(
        self, state, config, dataset_name: str,
        question: str, sub_questions: list, initial_prompt: str,
        initial_context: str, stream_queue, node_id: str,
    ) -> tuple[str, int]:
        """IRCoT 迭代检索链式推理"""
        from rag.rag_models.retrieval.prompt_builder import (
            build_prompt, generate_answer_stream,
        )
        from rag.rag_models.retrieval.retrieval_core import (
            process_retrieval_results,
        )

        max_steps = getattr(config.retrieval.agent, "max_steps", 5)
        accumulated_context = initial_context
        current_prompt = initial_prompt
        current_query = question
        full_answer = ""
        step_count = 0

        await self._push_token(stream_queue, node_id, "🔄 IRCoT 迭代检索开始...\n")

        for step in range(max_steps + 1):
            step_count = step
            step_text = ""

            # 流式生成推理
            try:
                async for token in state.llm_stream_client.call_api_stream(
                    current_prompt,
                ):
                    if token:
                        step_text += token
                        await self._push_token(stream_queue, node_id, token)
            except Exception as e:
                logger.error("IRCoT 步骤 %d 失败: %s", step, e)
                full_answer += step_text
                break

            full_answer = step_text

            # 检查是否已找到答案
            answer_match = re.search(rf"{re.escape(_ANSWER_MARKER)}\s*(.+?)(?:$|\n)", step_text)
            if answer_match:
                await self._push_token(
                    stream_queue, node_id,
                    f"\n\n✅ 在第 {step + 1} 步找到答案\n",
                )
                return answer_match.group(1).strip(), step + 1

            # 提取新查询
            query_match = re.search(rf"{re.escape(_QUERY_MARKER)}\s*(.+?)(?:$|\n)", step_text)
            if not query_match:
                await self._push_token(
                    stream_queue, node_id,
                    "\n\n✅ LLM 未提出新查询，结束迭代\n",
                )
                break

            new_query = query_match.group(1).strip()
            if not new_query or new_query == current_query:
                await self._push_token(
                    stream_queue, node_id, "\n\n✅ 查询无变化，结束迭代\n",
                )
                break

            current_query = new_query
            await self._push_token(
                stream_queue, node_id,
                f"\n\n🔄 第 {step + 2} 轮检索: {new_query}\n",
            )

            # 用新查询检索
            try:
                ret_results, _ = process_retrieval_results(
                    state=state, question=new_query,
                    involved_types={}, retrieval_type="micro",
                )
                new_triples = ret_results.get("triples", [])
                new_chunks = ret_results.get("chunk_contents", {})

                # 更新上下文
                extra = []
                if new_triples:
                    extra.append("## 新检索知识三元组\n" + "\n".join(new_triples))
                if new_chunks:
                    chunk_text = "\n\n".join(
                        f"[片段 {cid}]: {text}"
                        for cid, text in new_chunks.items() if text
                    )
                    if chunk_text:
                        extra.append("## 新检索原文片段\n" + chunk_text)
                accumulated_context += "\n\n" + "\n\n".join(extra)

                current_prompt = build_prompt(
                    config=config, dataset=dataset_name,
                    question=question, sub_questions=sub_questions,
                    context=accumulated_context,
                )
            except Exception as e:
                logger.error("IRCoT 重检索失败: %s", e)
                break

        return full_answer, step_count + 1

    @staticmethod
    async def _push_token(stream_queue, node_id: str, token: str):
        """向 SSE 流推送 token"""
        if stream_queue is None or not token:
            return
        await stream_queue.put({
            "event": WorkflowEventType.NODE_OUTPUT,
            "data": json.dumps({"node_id": node_id, "token": token}, ensure_ascii=False),
        })
