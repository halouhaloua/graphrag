import json

from agentscope.message import UserMsg
from loguru import logger

from chronicle_writer.agents.factory import (
    create_coordinator,
    create_researcher,
    create_drafter,
    create_reviewer,
    create_relevance_filter,
)
from chronicle_writer.utils import decompose_topic, micro_filter
from chronicle_writer.tools.rag_recall import ircot_recall
from chronicle_writer.event_queue import push_event
from chronicle_writer.workflow.state import ChronicleWritingState


def _append_report(state: ChronicleWritingState, line: str) -> None:
    state["report"] = (state.get("report") or "") + line + "\n"


def _aspects_to_flat_items(aspects: list[dict]) -> list[dict]:
    """将 aspects 摊平成扁平 item 列表供 filter_relevance 使用"""
    items = []
    for a in aspects:
        for i, t in enumerate(a.get("triples", [])):
            items.append(
                {
                    "id": f"{a['name']}/triple_{i}",
                    "content": t,
                    "source_aspect": a["name"],
                }
            )
        for i, c in enumerate(a.get("chunks", [])):
            items.append(
                {
                    "id": f"{a['name']}/chunk_{i}",
                    "content": c[:500],
                    "source_aspect": a["name"],
                }
            )
    return items


async def _persist_section(
    state: ChronicleWritingState,
    section_id: str,
    title: str,
    level: int,
    sort_order: int,
    content: str,
) -> None:
    """将章节内容 upsert 到 chronicle_sections 表（不阻断工作流）。"""
    from chronicle_writer.model import ChronicleSection
    from chronicle_writer.tools.reference_tool import _db_factory
    from sqlalchemy import select

    try:
        async with _db_factory() as db:
            stmt = select(ChronicleSection).where(
                ChronicleSection.project_id == state["project_id"],
                ChronicleSection.sort_order == sort_order,
                ChronicleSection.is_deleted.is_(False),
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                existing.title = title
                existing.content = content
                existing.word_count = len(content or "")
                existing.status = "done"
            else:
                section = ChronicleSection(
                    project_id=state["project_id"],
                    title=title,
                    level=level,
                    sort_order=sort_order,
                    content=content or "",
                    status="done",
                    word_count=len(content or ""),
                )
                db.add(section)
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to persist section {section_id}: {e}")
        state["errors"].append(f"persist_section_{section_id}: {e}")


async def _rebuild_section_tree(state: ChronicleWritingState) -> None:
    """根据 level 层级关系，推算 sections 的 parent_id。"""
    from chronicle_writer.model import ChronicleSection
    from chronicle_writer.tools.reference_tool import _db_factory
    from sqlalchemy import select

    try:
        async with _db_factory() as db:
            stmt = (
                select(ChronicleSection)
                .where(
                    ChronicleSection.project_id == state["project_id"],
                    ChronicleSection.is_deleted.is_(False),
                )
                .order_by(ChronicleSection.sort_order)
            )
            sections = (await db.execute(stmt)).scalars().all()
            last_at_level: dict[int, str] = {}
            changed = False
            for s in sections:
                parent_id = last_at_level.get(s.level - 1)
                if parent_id and s.parent_id != parent_id:
                    s.parent_id = parent_id
                    changed = True
                elif not parent_id and s.parent_id is not None:
                    s.parent_id = None
                    changed = True
                last_at_level[s.level] = s.id
            if changed:
                await db.commit()
    except Exception as e:
        logger.warning(f"Failed to rebuild section tree: {e}")


async def _log_stage(
    state: ChronicleWritingState,
    stage: str,
    event_type: str,
    message: str = "",
) -> None:
    """将阶段日志写入 chronicle_workflow_logs 表。

    Args:
        state: 工作流状态
        stage: 节点名称（如 plan_project）
        event_type: start / complete / error
        message: 日志消息
    """
    from chronicle_writer.model import ChronicleWorkflowLog
    from chronicle_writer.tools.reference_tool import _db_factory

    try:
        async with _db_factory() as db:
            log = ChronicleWorkflowLog(
                project_id=state["project_id"],
                stage=stage,
                event_type=event_type,
                message=message,
            )
            db.add(log)
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to write log ({stage}/{event_type}): {e}")


async def _persist_reviews(state: ChronicleWritingState) -> None:
    """将审校结果批量写入 chronicle_reviews 表。

    先软删除该项目的旧审查记录（修订场景），再写入当前结果。
    """
    from chronicle_writer.model import ChronicleReview
    from chronicle_writer.tools.reference_tool import _db_factory
    from sqlalchemy import update as sql_update

    try:
        async with _db_factory() as db:
            await db.execute(
                sql_update(ChronicleReview)
                .where(ChronicleReview.project_id == state["project_id"])
                .values(is_deleted=True)
            )
            for r in state.get("review_results", []):
                review = ChronicleReview(
                    project_id=state["project_id"],
                    section_id=r.get("section_id"),
                    review_type=r.get("review_type", "fact"),
                    reviewer_agent="reviewer",
                    issue=r.get("issue", ""),
                    severity=r.get("severity", "minor"),
                    suggestion=r.get("suggestion"),
                )
                db.add(review)
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to persist reviews: {e}")


async def _update_project_report(state: ChronicleWritingState) -> None:
    """将工作流报告和字数写入 chronicle_projects 表。"""
    from chronicle_writer.model import ChronicleProject
    from chronicle_writer.tools.reference_tool import _db_factory
    from sqlalchemy import select

    try:
        async with _db_factory() as db:
            stmt = select(ChronicleProject).where(
                ChronicleProject.id == state["project_id"],
                ChronicleProject.is_deleted.is_(False),
            )
            result = await db.execute(stmt)
            project = result.scalar_one_or_none()
            if project:
                project.report = state.get("report", "")
                project.word_count = sum(
                    len(c) for c in state.get("sections", {}).values()
                )
                project.status = "done"
                await db.commit()
    except Exception as e:
        logger.warning(f"Failed to update project report: {e}")


# ─── 循环条件判断 ───


def _decide_retrieve_next(state: ChronicleWritingState) -> str:
    """判断是否继续检索下一个方面"""
    idx = state.get("_aspect_idx", 0)
    total = len(state.get("_aspect_names", []))
    return "retrieve_aspect" if idx < total else "verify_evidence"


def _decide_write_next(state: ChronicleWritingState) -> str:
    """判断是否继续撰写下一节"""
    idx = state.get("_section_idx", 0)
    total = len(state.get("section_order", []))
    return "write_section" if idx < total else "generate_appendix"


# ─── ① 主编规划 ───


async def plan_project_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """① 主编规划 — 加载模板 + 生成凡例 + 生成篇目"""
    await _log_stage(state, "plan_project", "start")
    agent = create_coordinator()
    task = {
        "stage": "plan",
        "chronicle_type": state["chronicle_type"],
        "region_name": state["region_name"],
        "scope_description": state["scope_description"],
        "project_title": state["project_title"],
    }
    try:
        result = await agent.reply(
            UserMsg(name="user", content=json.dumps(task, ensure_ascii=False))
        )
        text = result.get_text_content() or "{}"
        parsed = json.loads(text)
        state["outline"] = parsed.get("outline", [])
        state["editorial_notes"] = parsed.get("editorial_notes", "")
        state["current_stage"] = "planning"
        state["progress"] = 0.05
        section_count = len(state["outline"])
        state["status_message"] = "凡例和篇目生成完毕"
        _append_report(state, f"[规划] 篇目规划完成: 共 {section_count} 节")
        await _log_stage(
            state, "plan_project", "complete", f"篇目规划完成: 共{section_count}节"
        )
        state["pending_events"].append(
            {
                "type": "status",
                "stage": "planning",
                "progress": 0.05,
                "message": "凡例和篇目生成完毕",
            }
        )
        state["pending_events"].append(
            {
                "type": "outline",
                "sections": state["outline"],
            }
        )
    except Exception as e:
        logger.error(f"plan_project_node failed: {e}")
        state["errors"].append(f"plan_project: {e}")
        state["status_message"] = f"规划失败: {e}"
        _append_report(state, f"[规划] 规划失败: {e}")
        await _log_stage(state, "plan_project", "error", str(e))
        state["pending_events"].append({"type": "error", "message": f"规划失败: {e}"})
    return state


# ─── ②-a 主题分解 ───


async def decompose_only_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """②-a 主题分解 — 将写作主题拆解为若干个检索方面"""
    await _log_stage(state, "decompose_only", "start")
    _append_report(state, "[检索] 开始主题分解...")

    aspects = decompose_topic(
        project_title=state["project_title"],
        scope_description=state["scope_description"],
        outline=state.get("outline", []),
    )
    names = [a["name"] for a in aspects]
    queries = {a["name"]: a["recall_query"] for a in aspects}

    state["_aspect_names"] = names
    state["_aspect_queries"] = queries
    state["_aspect_idx"] = 0
    state["aspects"] = []
    state["current_stage"] = "decomposing"
    state["progress"] = 0.08
    state["status_message"] = f"主题分解为 {len(names)} 个方面"

    _append_report(state, f"[检索] 主题分解: 拆解为 {len(names)} 个方面")
    await _log_stage(state, "decompose_only", "complete", f"拆解为{len(names)}个方面")

    state["pending_events"].append(
        {
            "type": "status",
            "stage": "decomposing",
            "progress": 0.08,
            "message": f"主题分解为 {len(names)} 个方面",
            "aspects": names,
        }
    )

    return state


# ─── ②-b 逐方面检索 ───


async def retrieve_aspect_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """②-b 逐方面检索 + 微审计 — 单个方面"""
    await _log_stage(state, "retrieve_aspect", "start")
    idx = state["_aspect_idx"]
    names = state.get("_aspect_names", [])
    queries = state.get("_aspect_queries", {})

    if idx >= len(names):
        return state

    name = names[idx]
    query = queries.get(name, "")
    total = max(len(names), 1)

    try:
        result = await ircot_recall(query, state.get("kb_ids"))
        raw_triples = result.get("triples", [])
        raw_chunks = result.get("chunk_contents", [])
    except Exception as e:
        logger.error(f"ircot_recall failed for aspect '{name}': {e}")
        raw_triples = []
        raw_chunks = []

    # 微审计
    decisions = micro_filter(name, raw_triples, raw_chunks)
    kept_triples = []
    kept_chunks = []
    aspect_removed = []

    for d in decisions:
        is_triple = d["id"].startswith("triple_")
        is_chunk = d["id"].startswith("chunk_")
        if not is_triple and not is_chunk:
            logger.warning(f"Unknown decision id format: {d.get('id')}, aspect={name}")
            continue
        if is_triple:
            idx_t = int(d["id"].split("_")[1])
            if idx_t >= len(raw_triples):
                continue
            content = raw_triples[idx_t]
        else:
            idx_c = int(d["id"].split("_")[1])
            if idx_c >= len(raw_chunks):
                continue
            content = raw_chunks[idx_c]
        if d.get("keep"):
            if is_triple:
                kept_triples.append(content)
            else:
                kept_chunks.append(content)
        else:
            aspect_removed.append(
                {
                    "id": d["id"],
                    "aspect": name,
                    "content": content,
                    "reason": d.get("reason", "不相关"),
                }
            )

    aspect_entry = {
        "name": name,
        "recall_query": query,
        "triples": kept_triples,
        "chunks": kept_chunks,
        "triple_count": len(raw_triples),
        "chunk_count": len(raw_chunks),
        "kept_count": len(kept_triples) + len(kept_chunks),
        "removed_count": len(aspect_removed),
    }

    state.setdefault("aspects", []).append(aspect_entry)
    state["removed_items"] = (state.get("removed_items") or []) + aspect_removed
    state["_aspect_idx"] = idx + 1
    state["current_stage"] = "retrieving"

    progress = 0.08 + 0.17 * (idx + 1) / total
    state["progress"] = round(progress, 2)
    state["status_message"] = (
        f"检索方面「{name}」: 保留 {aspect_entry['kept_count']} 条"
    )

    _append_report(
        state,
        f"[检索]   {name}: 召回 {aspect_entry['triple_count']} 条三元组 + "
        f"{aspect_entry['chunk_count']} 段原文，"
        f"保留 {aspect_entry['kept_count']} 条，移除 {aspect_entry['removed_count']} 条",
    )
    if aspect_removed:
        state.setdefault("report_details", []).append(
            {
                "summary": f"[检索] {name}: 移除 {len(aspect_removed)} 条",
                "details": [
                    f"移除: {d['content'][:80]} — {d['reason']}" for d in aspect_removed
                ],
            }
        )

    state["pending_events"].append(
        {
            "type": "status",
            "stage": "retrieving",
            "progress": state["progress"],
            "message": f"检索方面「{name}」: 保留 {aspect_entry['kept_count']} 条",
            "aspect": name,
        }
    )

    await _log_stage(state, "retrieve_aspect", "complete", f"方面「{name}」检索完成")
    return state


# ─── ③ 史料考证 ───


async def verify_evidence_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """③ 史料考证 — 遍历 aspects 做事实验证"""
    await _log_stage(state, "verify_evidence", "start")
    agent = create_researcher()
    task = {
        "stage": "verify",
        "aspects": state.get("aspects", []),
        "kb_ids": state.get("kb_ids", []),
    }
    try:
        result = await agent.reply(
            UserMsg(name="user", content=json.dumps(task, ensure_ascii=False))
        )
        text = result.get_text_content() or "{}"
        data = json.loads(text)
        state["verified_data"] = data.get("verified_data", {})
        state["contradictions"] = data.get("contradictions", [])
        state["current_stage"] = "verifying"
        state["progress"] = 0.40

        verified_count = len(state.get("verified_data", {}))
        contra_count = len(state.get("contradictions", []))
        if contra_count:
            state["status_message"] = (
                f"事实核查完成: {verified_count} 条验证通过，发现 {contra_count} 处矛盾"
            )
            _append_report(
                state, f"[验证] 验证 {verified_count} 条，发现 {contra_count} 处矛盾"
            )
            state.setdefault("report_details", []).append(
                {
                    "summary": f"[验证] 发现 {contra_count} 处矛盾",
                    "details": [
                        f"矛盾: {c.get('description', '')}"
                        for c in state.get("contradictions", [])
                    ],
                }
            )
            await _log_stage(
                state,
                "verify_evidence",
                "complete",
                f"验证{verified_count}条，发现{contra_count}处矛盾",
            )
        else:
            state["status_message"] = f"事实核查完成: {verified_count} 条全部通过"
            _append_report(state, f"[验证] 验证 {verified_count} 条，全部通过")
            await _log_stage(
                state,
                "verify_evidence",
                "complete",
                f"验证{verified_count}条，全部通过",
            )
    except Exception as e:
        logger.error(f"verify_evidence_node failed: {e}")
        state["errors"].append(f"verify_evidence: {e}")
        _append_report(state, f"[验证] 验证失败: {e}")
        await _log_stage(state, "verify_evidence", "error", str(e))
        state["pending_events"].append(
            {"type": "error", "message": f"史料考证失败: {e}"}
        )
    return state


# ─── ④ 相关度审校 ───


async def filter_relevance_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """④ 相关度审校 + 跨方面矛盾检测"""
    await _log_stage(state, "filter_relevance", "start")
    aspects = state.get("aspects", [])
    items = _aspects_to_flat_items(aspects)

    if not items:
        state["filtered_data"] = {}
        state["current_stage"] = "filtering"
        state["progress"] = 0.50
        _append_report(state, "[审校] 无待审校数据，跳过")
        await _log_stage(state, "filter_relevance", "complete", "无待审校数据")
        return state

    agent = create_relevance_filter()
    task = {
        "project_title": state["project_title"],
        "outline": state.get("outline", []),
        "items": items,
    }
    try:
        result = await agent.reply(
            UserMsg(name="user", content=json.dumps(task, ensure_ascii=False))
        )
        text = result.get_text_content() or "[]"
        decisions = json.loads(text)
        if not isinstance(decisions, list):
            decisions = []
    except Exception as e:
        logger.error(f"filter_relevance agent failed: {e}")
        decisions = [
            {
                "id": it["id"],
                "keep": True,
                "score": 1.0,
                "section_id": None,
                "reason": "降级：全部保留",
            }
            for it in items
        ]

    # 重组数据
    filtered: dict = {}
    removed: list[dict] = []
    item_map = {it["id"]: it for it in items}

    for d in decisions:
        item = item_map.get(d.get("id", ""))
        if not item:
            continue
        if d.get("keep"):
            sec_id = d.get("section_id") or "ungrouped"
            filtered.setdefault(sec_id, []).append(
                {
                    "content": item["content"],
                    "score": d.get("score", 1.0),
                    "aspect": item["source_aspect"],
                }
            )
        else:
            removed.append(
                {
                    "id": d["id"],
                    "aspect": item["source_aspect"],
                    "content": item["content"],
                    "reason": d.get("reason", "不相关"),
                }
            )

    state["filtered_data"] = filtered
    state["removed_items"] = (state.get("removed_items") or []) + removed

    # 跨方面矛盾检测
    section_aspects: dict[str, set] = {}
    for sec_id, sec_items in filtered.items():
        section_aspects[sec_id] = {it["aspect"] for it in sec_items}

    contradictions = state.get("contradictions") or []
    for sec_id, aspects_set in section_aspects.items():
        if len(aspects_set) > 1:
            contradictions.append(
                {
                    "type": "cross_aspect",
                    "section_id": sec_id,
                    "aspects": list(aspects_set),
                    "severity": "info",
                    "description": f"章节 {sec_id} 包含来自多个方面的数据，建议检查一致性",
                }
            )
    state["contradictions"] = contradictions

    state["current_stage"] = "filtering"
    state["progress"] = 0.50

    kept_count = sum(len(v) for v in filtered.values())
    removed_count = len(removed)
    _append_report(
        state, f"[审校] 相关度终审完成: 保留 {kept_count} 条，移除 {removed_count} 条"
    )
    if contradictions:
        _append_report(state, f"[审校] 跨方面矛盾检测: {len(contradictions)} 处")
    _append_report(
        state,
        f"[审校] 最终分布: {', '.join(f'{k}({len(v)}条)' for k, v in filtered.items())}",
    )

    state["status_message"] = (
        f"相关度审校完成: 保留 {kept_count} 条，移除 {removed_count} 条"
    )
    state["pending_events"].append(
        {
            "type": "status",
            "stage": "filtering",
            "progress": 0.50,
            "message": f"相关度审校完成，保留 {kept_count} 条，移除 {removed_count} 条",
        }
    )
    state["pending_events"].append(
        {
            "type": "relevance_filter",
            "section_summary": {k: len(v) for k, v in filtered.items()},
            "removed_count": removed_count,
        }
    )

    await _log_stage(
        state,
        "filter_relevance",
        "complete",
        f"保留{kept_count}条，移除{removed_count}条",
    )
    return state


# ─── ⑤-a 撰写准备 ───


async def write_sections_coord_node(
    state: ChronicleWritingState,
) -> ChronicleWritingState:
    """⑤-a 撰写准备 — 确定章节顺序"""
    await _log_stage(state, "write_sections_coord", "start")
    section_order = state.get("section_order", [])
    if not section_order and state["outline"]:
        section_order = [
            s.get("id", f"sec_{i}")
            for i, s in enumerate(state["outline"])
            if s.get("level", 1) >= 1
        ]
        state["section_order"] = section_order

    # 软清理该项目的旧章节（修订/重跑场景）
    from chronicle_writer.model import ChronicleSection
    from chronicle_writer.tools.reference_tool import _db_factory
    from sqlalchemy import update as sql_update

    try:
        async with _db_factory() as db:
            await db.execute(
                sql_update(ChronicleSection)
                .where(ChronicleSection.project_id == state["project_id"])
                .values(is_deleted=True)
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to clean old sections: {e}")

    state["_section_idx"] = 0
    state["current_stage"] = "drafting"
    state["progress"] = 0.50
    state["status_message"] = f"准备撰写 {len(section_order)} 节"
    await _log_stage(
        state, "write_sections_coord", "complete", f"准备撰写{len(section_order)}节"
    )

    return state


# ─── ⑤-b 逐节撰写 ───


async def write_section_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """⑤-b 逐节撰写 — 当前一节"""
    await _log_stage(state, "write_section", "start")
    idx = state["_section_idx"]
    section_order = state.get("section_order", [])

    if idx >= len(section_order):
        return state

    section_id = section_order[idx]
    total = max(len(section_order), 1)

    # 优先使用过滤后的数据
    research_source = state.get("filtered_data") or state.get("verified_data") or {}

    section_info = {"id": section_id}
    for s in state.get("outline", []):
        if s.get("id") == section_id:
            section_info = s
            break

    agent = create_drafter()
    task = {
        "stage": "write",
        "section_id": section_id,
        "section_title": section_info.get("title", ""),
        "outline": state.get("outline", []),
        "research_data": research_source,
        "project_id": state["project_id"],
    }

    accumulated = ""
    try:
        async for event in agent.reply_stream(
            UserMsg(name="user", content=json.dumps(task, ensure_ascii=False))
        ):
            if hasattr(event, "delta") and event.delta:
                accumulated += event.delta
                await push_event(
                    {
                        "type": "token",
                        "section_id": section_id,
                        "text": event.delta,
                    }
                )

        content = accumulated
        # 持久化到 chronicle_sections
        await _persist_section(
            state=state,
            section_id=section_id,
            title=section_info.get("title", ""),
            level=section_info.get("level", 1),
            sort_order=idx,
            content=content,
        )
        state["sections"][section_id] = content
        state["_section_idx"] = idx + 1
        state["current_section_idx"] = idx
        state["progress"] = 0.50 + 0.30 * (idx + 1) / total
        state["status_message"] = f"撰写第 {idx + 1}/{total} 节"

        state["pending_events"].append(
            {
                "type": "section_complete",
                "section_id": section_id,
                "title": section_info.get("title", ""),
                "word_count": len(content),
            }
        )
        await _log_stage(
            state,
            "write_section",
            "complete",
            f"第{idx + 1}节「{section_info.get('title', '')}」完成",
        )
    except Exception as e:
        logger.error(f"write section {section_id} failed: {e}")
        state["errors"].append(f"write_section_{section_id}: {e}")
        state["sections"][section_id] = ""
        state["_section_idx"] = idx + 1
        state["current_section_idx"] = idx
        state["pending_events"].append(
            {"type": "error", "message": f"章节撰写失败: {e}"}
        )
        await _log_stage(state, "write_section", "error", str(e))
        # 空内容也持久化，标记失败
        await _persist_section(
            state=state,
            section_id=section_id,
            title=section_info.get("title", ""),
            level=section_info.get("level", 1),
            sort_order=idx,
            content="",
        )

    return state


# ─── ⑥ 图表凡例 ───


async def generate_appendix_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """⑥ 图表凡例 — 生成撰写统计报告"""
    await _log_stage(state, "generate_appendix", "start")
    section_order = state.get("section_order", [])
    total_words = sum(len(c) for c in state.get("sections", {}).values())
    _append_report(
        state, f"[撰写] 共撰写 {len(section_order)} 节，总计 {total_words} 字"
    )

    # 根据 level 推算 sections 的 parent_id
    await _rebuild_section_tree(state)

    state["current_stage"] = "appendix"
    state["progress"] = 0.82
    state["status_message"] = "图表凡例生成完毕"
    await _log_stage(state, "generate_appendix", "complete")
    return state


# ─── ⑦ 统稿合成 ───


async def compile_document_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """⑦ 统稿合成"""
    await _log_stage(state, "compile_document", "start")
    agent = create_coordinator()
    task = {
        "stage": "compile",
        "sections": state["sections"],
        "outline": state["outline"],
        "project_title": state["project_title"],
    }
    try:
        result = await agent.reply(
            UserMsg(name="user", content=json.dumps(task, ensure_ascii=False))
        )
        text = result.get_text_content() or "{}"
        data = json.loads(text)
        if "compiled_sections" in data:
            state["sections"].update(data["compiled_sections"])
        state["current_stage"] = "compiling"
        state["progress"] = 0.88
        state["status_message"] = "统稿合成完成"
        _append_report(state, "[统稿] 统稿合成完成")
        await _log_stage(state, "compile_document", "complete")
    except Exception as e:
        logger.error(f"compile_document_node failed: {e}")
        state["errors"].append(f"compile: {e}")
        _append_report(state, f"[统稿] 统稿失败: {e}")
        await _log_stage(state, "compile_document", "error", str(e))
        state["pending_events"].append(
            {"type": "error", "message": f"统稿合成失败: {e}"}
        )
    return state


# ─── ⑧ 校审核对 ───


async def review_document_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """⑧ 校审核对"""
    await _log_stage(state, "review_document", "start")
    agent = create_reviewer()
    task = {
        "stage": "review",
        "sections": state["sections"],
        "kb_ids": state.get("kb_ids", []),
        "project_id": state["project_id"],
    }
    try:
        result = await agent.reply(
            UserMsg(name="user", content=json.dumps(task, ensure_ascii=False))
        )
        text = result.get_text_content() or "{}"
        data = json.loads(text)
        state["review_results"] = data.get("review_results", [])
        state["iteration_count"] = state.get("iteration_count", 0) + 1
        state["current_stage"] = "reviewing"
        state["progress"] = 0.94
        issue_count = len(state["review_results"])
        state["status_message"] = f"审校完成，发现 {issue_count} 个问题"
        _append_report(state, f"[审查] 审查发现 {issue_count} 个问题")
        state.setdefault("report_details", []).append(
            {
                "summary": f"[审查] 发现 {issue_count} 个问题",
                "details": [
                    f"[{r.get('severity', '')}] {r.get('issue', '')[:100]}"
                    for r in state.get("review_results", [])
                ],
            }
        )
        await _persist_reviews(state)
        await _log_stage(
            state,
            "review_document",
            "complete",
            f"发现{issue_count}个问题",
        )
        state["pending_events"].append(
            {
                "type": "review",
                "results": state["review_results"],
            }
        )
    except Exception as e:
        logger.error(f"review_document_node failed: {e}")
        state["errors"].append(f"review: {e}")
        state["status_message"] = f"审校失败: {e}"
        _append_report(state, f"[审查] 审查失败: {e}")
        await _log_stage(state, "review_document", "error", str(e))
        state["pending_events"].append({"type": "error", "message": f"审校失败: {e}"})
    return state


# ─── ⑨ 质检归档 ───


async def quality_check_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """⑨ 质检归档"""
    await _log_stage(state, "quality_check", "start")
    total_sections = len(state.get("sections", {}))
    written_sections = sum(1 for c in state["sections"].values() if c.strip())
    word_count = sum(len(c) for c in state["sections"].values())

    section_ratio = written_sections / max(total_sections, 1)
    critical_issues = len(
        [r for r in state.get("review_results", []) if r.get("severity") == "critical"]
    )
    review_ratio = 1.0 - (
        critical_issues / max(len(state.get("review_results", [])), 1)
    )

    state["quality_score"] = round(section_ratio * 0.6 + review_ratio * 0.4, 2)
    state["quality_checks"] = [
        {
            "name": "章节完成度",
            "pass": section_ratio >= 0.8,
            "value": f"{section_ratio:.0%}",
        },
        {"name": "总字数", "pass": word_count >= 1000, "value": f"{word_count}字"},
        {
            "name": "严重问题",
            "pass": review_ratio >= 0.8,
            "value": f"{critical_issues}个",
        },
    ]
    state["current_stage"] = "quality"
    state["progress"] = 0.97
    score = state["quality_score"]
    state["status_message"] = f"质检评分: {score}"
    _append_report(state, f"[质检] 质检评分: {score}")
    await _log_stage(state, "quality_check", "complete", f"评分{score}")
    state["pending_events"].append(
        {
            "type": "quality",
            "score": score,
            "checks": state["quality_checks"],
        }
    )
    return state


# ─── ⑩ 最终交付 ───


async def finalize_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """⑩ 最终交付"""
    await _log_stage(state, "finalize", "start")
    word_count = sum(len(c) for c in state.get("sections", {}).values())
    state["current_stage"] = "completed"
    state["progress"] = 1.0
    state["status_message"] = "志书生成完成"
    _append_report(state, "[完成] 志书生成完毕")
    await _update_project_report(state)
    await _log_stage(state, "finalize", "complete", f"共{word_count}字")

    state["pending_events"].append(
        {
            "type": "done",
            "project_id": state["project_id"],
            "status": "completed",
            "word_count": word_count,
        }
    )
    state["pending_events"].append(
        {
            "type": "report",
            "report": state.get("report", ""),
        }
    )
    return state
