from langgraph.graph import StateGraph, END
from chronicle_writer.workflow.state import ChronicleWritingState
from chronicle_writer.workflow.nodes import (
    plan_project_node,
    collect_materials_node,
    verify_evidence_node,
    human_review_node,
    write_sections_node,
    generate_appendix_node,
    compile_document_node,
    review_document_node,
    quality_check_node,
    finalize_node,
)


def _has_critical_issues(state: ChronicleWritingState) -> bool:
    """检查是否有未解决的严重问题"""
    return any(
        r.get("severity") == "critical" and not r.get("resolved")
        for r in state.get("review_results", [])
    )


def _decide_human_review(state: ChronicleWritingState) -> str:
    """③→④/⑤: 是否需要人工复核"""
    contradictions = state.get("contradictions", [])
    if contradictions and len(contradictions) > 0:
        return "interrupt"
    return "proceed"


def _decide_after_human_review(state: ChronicleWritingState) -> str:
    """④→③/⑤: 人工复核决策"""
    decision = state.get("human_decision", {})
    action = decision.get("action", "override")
    if action == "retry":
        return "retry_verify"
    return "override"


def _decide_revision_needed(state: ChronicleWritingState) -> str:
    """⑧→⑤/⑨: 审校后是否需修订（不篡改 state，递增已在 review_document_node 完成）"""
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
    builder.add_node("collect_materials", collect_materials_node)
    builder.add_node("verify_evidence", verify_evidence_node)
    builder.add_node("human_review", human_review_node)
    builder.add_node("write_sections", write_sections_node)
    builder.add_node("generate_appendix", generate_appendix_node)
    builder.add_node("compile_document", compile_document_node)
    builder.add_node("review_document", review_document_node)
    builder.add_node("quality_check", quality_check_node)
    builder.add_node("finalize", finalize_node)

    builder.set_entry_point("plan_project")

    builder.add_edge("plan_project", "collect_materials")
    builder.add_edge("collect_materials", "verify_evidence")

    builder.add_conditional_edges(
        "verify_evidence",
        _decide_human_review,
        {
            "interrupt": "human_review",
            "proceed": "write_sections",
        },
    )

    builder.add_conditional_edges(
        "human_review",
        _decide_after_human_review,
        {
            "retry_verify": "verify_evidence",
            "override": "write_sections",
        },
    )

    builder.add_edge("write_sections", "generate_appendix")
    builder.add_edge("generate_appendix", "compile_document")
    builder.add_edge("compile_document", "review_document")

    builder.add_conditional_edges(
        "review_document",
        _decide_revision_needed,
        {
            "revise": "write_sections",
            "proceed": "quality_check",
        },
    )

    builder.add_conditional_edges(
        "quality_check",
        _decide_quality_pass,
        {
            "revise": "write_sections",
            "deliver": "finalize",
        },
    )

    builder.add_edge("finalize", END)

    return builder.compile()
