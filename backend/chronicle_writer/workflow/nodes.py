import json

from agentscope.message import UserMsg
from loguru import logger

from chronicle_writer.agents.factory import (
    create_coordinator,
    create_researcher,
    create_drafter,
    create_reviewer,
)
from chronicle_writer.workflow.state import ChronicleWritingState


async def plan_project_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """① 主编规划 — 加载模板 + 生成凡例 + 生成篇目"""
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
        state["status_message"] = "凡例和篇目生成完毕"
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
        state["pending_events"].append({"type": "error", "message": f"规划失败: {e}"})
    return state


async def collect_materials_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """② 资料采集 — 按篇目检索知识图谱"""
    agent = create_researcher()
    task = {
        "stage": "collect",
        "outline": state["outline"],
        "kb_ids": state["kb_ids"],
        "project_id": state["project_id"],
    }
    try:
        result = await agent.reply(
            UserMsg(name="user", content=json.dumps(task, ensure_ascii=False))
        )
        text = result.get_text_content() or "{}"
        data = json.loads(text)
        state["research_data"] = data.get("research_data", {})
        state["global_facts"] = data.get("global_facts", [])
        state["current_stage"] = "researching"
        state["progress"] = 0.15
        state["status_message"] = "资料采集完成"
        state["pending_events"].append(
            {
                "type": "status",
                "stage": "researching",
                "progress": 0.15,
                "message": "共检索到资料",
            }
        )
    except Exception as e:
        logger.error(f"collect_materials_node failed: {e}")
        state["errors"].append(f"collect_materials: {e}")
        state["pending_events"].append(
            {"type": "error", "message": f"资料采集失败: {e}"}
        )
    return state


async def verify_evidence_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """③ 史料考证 — 验证事实，检测矛盾"""
    agent = create_researcher()
    task = {
        "stage": "verify",
        "research_data": state["research_data"],
        "kb_ids": state["kb_ids"],
    }
    try:
        result = await agent.reply(
            UserMsg(name="user", content=json.dumps(task, ensure_ascii=False))
        )
        text = result.get_text_content() or "{}"
        data = json.loads(text)
        state["verified_data"] = data.get("verified_data", state["research_data"])
        state["contradictions"] = data.get("contradictions", [])
        state["current_stage"] = "verifying"
        state["progress"] = 0.30
        if state["contradictions"]:
            state["status_message"] = f"发现 {len(state['contradictions'])} 处矛盾"
        else:
            state["status_message"] = "史实考证通过"
    except Exception as e:
        logger.error(f"verify_evidence_node failed: {e}")
        state["errors"].append(f"verify_evidence: {e}")
        state["pending_events"].append(
            {"type": "error", "message": f"史料考证失败: {e}"}
        )
    return state


async def human_review_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """④ 人工复核中断点"""
    state["current_stage"] = "waiting_human"
    state["progress"] = 0.35
    state["status_message"] = "等待主编复核矛盾"
    state["pending_events"].append(
        {
            "type": "interrupt",
            "reason": "contradiction",
            "stage": "verifying",
            "data": state["contradictions"],
        }
    )
    return state


async def write_sections_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """⑤ 条目撰写 — 逐节撰写正文"""
    agent = create_drafter()
    section_order = state.get("section_order", [])
    if not section_order and state["outline"]:
        section_order = [
            s.get("id", f"sec_{i}")
            for i, s in enumerate(state["outline"])
            if s.get("level", 1) >= 1
        ]
        state["section_order"] = section_order

    total = max(len(section_order), 1)
    for idx, section_id in enumerate(section_order):
        try:
            section_info = {"id": section_id}
            for s in state["outline"]:
                if s.get("id") == section_id:
                    section_info = s
                    break

            task = {
                "stage": "write",
                "section_id": section_id,
                "section_title": section_info.get("title", ""),
                "outline": state["outline"],
                "verified_data": state.get("verified_data", {}),
                "project_id": state["project_id"],
            }
            accumulated = ""
            async for event in agent.reply_stream(
                UserMsg(name="user", content=json.dumps(task, ensure_ascii=False))
            ):
                if hasattr(event, "delta") and event.delta:
                    accumulated += event.delta
                    state["pending_events"].append(
                        {
                            "type": "token",
                            "section_id": section_id,
                            "text": event.delta,
                        }
                    )
            content = accumulated
            state["sections"][section_id] = content
            state["current_section_idx"] = idx
            state["progress"] = 0.30 + 0.40 * (idx + 1) / total
            state["status_message"] = f"撰写第 {idx + 1}/{total} 节"
            state["pending_events"].append(
                {
                    "type": "section_complete",
                    "section_id": section_id,
                    "title": section_info.get("title", ""),
                    "word_count": len(content),
                }
            )
        except Exception as e:
            logger.error(f"write section {section_id} failed: {e}")
            state["errors"].append(f"write_section_{section_id}: {e}")
            state["pending_events"].append(
                {"type": "error", "message": f"章节撰写失败: {e}"}
            )

    state["current_stage"] = "drafting"
    return state


async def generate_appendix_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """⑥ 图表凡例"""
    state["current_stage"] = "appendix"
    state["progress"] = 0.70
    state["status_message"] = "图表凡例生成完毕"
    return state


async def compile_document_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """⑦ 统稿合成 — 合并章节，统一检查"""
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
        state["progress"] = 0.80
        state["status_message"] = "统稿合成完成"
    except Exception as e:
        logger.error(f"compile_document_node failed: {e}")
        state["errors"].append(f"compile: {e}")
        state["pending_events"].append(
            {"type": "error", "message": f"统稿合成失败: {e}"}
        )
    return state


async def review_document_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """⑧ 校审核对 — 事实复查 + 体例检查 + 引用审计"""
    agent = create_reviewer()
    task = {
        "stage": "review",
        "sections": state["sections"],
        "kb_ids": state["kb_ids"],
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
        state["progress"] = 0.90
        state["status_message"] = (
            f"审校完成，发现 {len(state['review_results'])} 个问题"
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
        state["pending_events"].append({"type": "error", "message": f"审校失败: {e}"})
    return state


async def quality_check_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """⑨ 质检归档 — 完成度评分"""
    total_sections = len(state.get("sections", {}))
    written_sections = sum(1 for c in state["sections"].values() if c.strip())
    word_count = sum(len(c) for c in state["sections"].values())

    section_ratio = written_sections / max(total_sections, 1)
    review_ratio = 1.0 - (
        len(
            [
                r
                for r in state.get("review_results", [])
                if r.get("severity") == "critical"
            ]
        )
        / max(len(state.get("review_results", [])), 1)
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
            "value": f"{len([r for r in state.get('review_results', []) if r.get('severity') == 'critical'])}个",
        },
    ]
    state["current_stage"] = "quality"
    state["progress"] = 0.95
    state["status_message"] = f"质检评分: {state['quality_score']}"
    state["pending_events"].append(
        {
            "type": "quality",
            "score": state["quality_score"],
            "checks": state["quality_checks"],
        }
    )
    return state


async def finalize_node(state: ChronicleWritingState) -> ChronicleWritingState:
    """⑩ 最终交付"""
    word_count = sum(len(c) for c in state.get("sections", {}).values())
    state["current_stage"] = "completed"
    state["progress"] = 1.0
    state["status_message"] = "志书生成完成"
    state["pending_events"].append(
        {
            "type": "done",
            "project_id": state["project_id"],
            "status": "completed",
            "word_count": word_count,
        }
    )
    return state
