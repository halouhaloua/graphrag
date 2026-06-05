from langgraph.graph import StateGraph, END
from chronicle_writer.workflow.state import ChronicleWritingState
from chronicle_writer.workflow.nodes import (
    plan_project_node,
    decompose_only_node,
    retrieve_aspect_node,
    verify_evidence_node,
    filter_relevance_node,
    write_sections_coord_node,
    write_section_node,
    generate_appendix_node,
    compile_document_node,
    review_document_node,
    quality_check_node,
    finalize_node,
    _decide_retrieve_next,
    _decide_write_next,
)


def _has_critical_issues(state: ChronicleWritingState) -> bool:
    """检查是否有未解决的严重问题"""
    return any(
        r.get("severity") == "critical" and not r.get("resolved")
        for r in state.get("review_results", [])
    )


def _decide_revision_needed(state: ChronicleWritingState) -> str:
    """⑧→⑤/⑨: 审校后是否需修订"""
    iteration = state.get("iteration_count", 0)
    max_iter = state.get("max_iterations", 3)

    if iteration >= max_iter:
        return "proceed"

    if _has_critical_issues(state):
        return "revise"

    return "proceed"


def _decide_quality_pass(state: ChronicleWritingState) -> str:
    """⑨→⑤/⑩: 质检是否通过"""
    score = state.get("quality_score", 0)
    threshold = 0.8
    iteration = state.get("iteration_count", 0)
    max_iter = state.get("max_iterations", 3)

    if score >= threshold:
        return "deliver"

    if iteration >= max_iter:
        return "deliver"

    return "revise"


def build_chronicle_graph() -> StateGraph:
    """构建志书写作工作流图"""
    builder = StateGraph(ChronicleWritingState)

    builder.add_node("plan_project", plan_project_node)
    builder.add_node("decompose_only", decompose_only_node)
    builder.add_node("retrieve_aspect", retrieve_aspect_node)
    builder.add_node("verify_evidence", verify_evidence_node)
    builder.add_node("filter_relevance", filter_relevance_node)
    builder.add_node("write_sections_coord", write_sections_coord_node)
    builder.add_node("write_section", write_section_node)
    builder.add_node("generate_appendix", generate_appendix_node)
    builder.add_node("compile_document", compile_document_node)
    builder.add_node("review_document", review_document_node)
    builder.add_node("quality_check", quality_check_node)
    builder.add_node("finalize", finalize_node)

    builder.set_entry_point("plan_project")

    # 规划 → 分解 → 逐方面检索循环
    builder.add_edge("plan_project", "decompose_only")
    builder.add_edge("decompose_only", "retrieve_aspect")
    builder.add_conditional_edges(
        "retrieve_aspect",
        _decide_retrieve_next,
        {
            "retrieve_aspect": "retrieve_aspect",
            "verify_evidence": "verify_evidence",
        },
    )

    builder.add_edge("verify_evidence", "filter_relevance")
    builder.add_edge("filter_relevance", "write_sections_coord")

    # 撰写准备 → 逐节撰写循环
    builder.add_edge("write_sections_coord", "write_section")
    builder.add_conditional_edges(
        "write_section",
        _decide_write_next,
        {
            "write_section": "write_section",
            "generate_appendix": "generate_appendix",
        },
    )

    builder.add_edge("generate_appendix", "compile_document")
    builder.add_edge("compile_document", "review_document")

    # revision 循环 → 回到撰写准备（重置 counter）
    builder.add_conditional_edges(
        "review_document",
        _decide_revision_needed,
        {
            "revise": "write_sections_coord",
            "proceed": "quality_check",
        },
    )

    builder.add_conditional_edges(
        "quality_check",
        _decide_quality_pass,
        {
            "revise": "write_sections_coord",
            "deliver": "finalize",
        },
    )

    builder.add_edge("finalize", END)

    return builder.compile()
