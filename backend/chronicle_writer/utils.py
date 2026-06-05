"""志书写作工具函数 — 主题分解与微审计"""

import json

from loguru import logger


def decompose_topic(
    project_title: str,
    scope_description: str,
    outline: list[dict],
) -> list[dict]:
    """将写作主题拆解为若干个检索方面。

    Args:
        project_title: 志书标题
        scope_description: 范围描述（写作重点）
        outline: 篇目大纲 [{id, title, description}]

    Returns:
        方面列表 [{"name": str, "recall_query": str}, ...]
    """
    try:
        from rag.utils.call_llm_api import LLMCompletionCall
    except ImportError:
        logger.warning("RAG module unavailable, using fallback decomposition")
        return _fallback_decompose(scope_description, outline)

    outline_text = _format_outline(outline)
    prompt = (
        "你是一个志书编纂的检索策略专家。请根据志书标题、范围描述和篇目大纲，"
        "将写作主题拆解成 3-7 个独立的检索方面。每个方面应覆盖不同的子主题，"
        "且彼此不重叠。\n\n"
        f"志书标题：{project_title}\n"
        f"范围描述：{scope_description}\n"
        f"篇目大纲：\n{outline_text}\n\n"
        "输出 JSON 数组，每个元素包含 name（方面名称）和 recall_query（用于知识图谱搜索的查询语句）：\n"
        '[{"name": "农业经济", "recall_query": "某地区农业经济产业结构"}, ...]'
    )

    try:
        llm = LLMCompletionCall()
        raw = llm.call_api(prompt)
        aspects = json.loads(raw)
        if not isinstance(aspects, list) or len(aspects) == 0:
            return _fallback_decompose(scope_description, outline)
        for a in aspects:
            a.setdefault("name", "综合")
            a.setdefault("recall_query", scope_description)
        return aspects
    except Exception as e:
        logger.error(f"decompose_topic LLM call failed: {e}")
        return _fallback_decompose(scope_description, outline)


def micro_filter(
    aspect_name: str,
    triples: list[str],
    chunks: list[str],
) -> list[dict]:
    """微审计 — 逐条判断召回内容是否与某方面相关。

    Args:
        aspect_name: 方面名称
        triples: 三元组字符串列表
        chunks: chunk 文本列表

    Returns:
        决策列表 [{"id": str, "keep": bool, "score": float, "reason": str}, ...]
    """
    try:
        from rag.utils.call_llm_api import LLMCompletionCall
    except ImportError:
        return _fallback_micro_filter(triples, chunks)

    if not triples and not chunks:
        return []

    items = []
    for i, t in enumerate(triples):
        items.append({"id": f"triple_{i}", "content": t})
    for i, c in enumerate(chunks):
        items.append({"id": f"chunk_{i}", "content": c[:500]})

    items_text = json.dumps(
        [{"id": it["id"], "content": it["content"]} for it in items],
        ensure_ascii=False,
    )

    prompt = (
        f"你是一个志书资料审校员。请判断以下每条内容是否与方面「{aspect_name}」相关。\n\n"
        f"评分标准：\n"
        f"- score ≥ 0.7: 直接相关，保留\n"
        f"- 0.5 ≤ score < 0.7: 背景参考，保留\n"
        f"- score < 0.5: 不相关，移除\n\n"
        f"输入内容：\n{items_text}\n\n"
        '输出 JSON 数组：[{"id": "triple_0", "keep": true, "score": 0.92, "reason": "直接相关"}, ...]'
    )

    try:
        llm = LLMCompletionCall()
        raw = llm.call_api(prompt)
        decisions = json.loads(raw)
        if not isinstance(decisions, list):
            return _fallback_micro_filter(triples, chunks)
        return decisions
    except Exception as e:
        logger.error(f"micro_filter LLM call failed for aspect '{aspect_name}': {e}")
        return _fallback_micro_filter(triples, chunks)


def _format_outline(outline: list[dict]) -> str:
    lines = []
    for s in outline:
        title = s.get("title", "未命名")
        desc = s.get("description", "")
        lines.append(f"- {title}" + (f": {desc}" if desc else ""))
    return "\n".join(lines)


def _fallback_decompose(
    scope_description: str,
    outline: list[dict],
) -> list[dict]:
    """LLM 调用失败时的降级：使用前 5 个篇目作为检索方面"""
    aspects = []
    for s in outline[:5]:
        title = s.get("title", "")
        if title:
            aspects.append(
                {"name": title, "recall_query": f"{scope_description} {title}"}
            )
    if not aspects:
        aspects.append({"name": "综合", "recall_query": scope_description})
    return aspects


def _fallback_micro_filter(
    triples: list[str],
    chunks: list[str],
) -> list[dict]:
    """LLM 调用失败的降级：全部保留"""
    decisions = []
    for i in range(len(triples)):
        decisions.append(
            {
                "id": f"triple_{i}",
                "keep": True,
                "score": 1.0,
                "reason": "降级：全部保留",
            }
        )
    for i in range(len(chunks)):
        decisions.append(
            {"id": f"chunk_{i}", "keep": True, "score": 1.0, "reason": "降级：全部保留"}
        )
    return decisions
