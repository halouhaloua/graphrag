from typing import TypedDict


class ChronicleWritingState(TypedDict):
    """LangGraph 工作流状态"""

    # 项目标识
    project_id: str
    project_title: str
    chronicle_type: str
    region_name: str
    scope_description: str

    # 检索范围
    kb_ids: list[str]
    file_ids: list[str]

    # 进度
    current_stage: str
    progress: float
    status_message: str

    # 规划产出
    outline: list[dict]
    editorial_notes: str

    # 检索 + 微审计（由 decompose_only + retrieve_aspect 循环生成）
    aspects: list[dict]
    # 每个 aspect: {
    #   "name": str,
    #   "recall_query": str,
    #   "triples": [str],
    #   "chunks": [str],
    #   "triple_count": int,
    #   "chunk_count": int,
    #   "kept_count": int,
    #   "removed_count": int,
    # }

    # 史料考证
    verified_data: dict
    contradictions: list[dict]

    # 相关度审校
    filtered_data: dict
    # {section_id: [{content, score, aspect}]}
    removed_items: list[dict]
    # [{id, aspect, content, reason}]

    # 子图循环内部追踪（由 decompose / write 子节点使用）
    _aspect_names: list[str]
    _aspect_queries: dict[str, str]
    _aspect_idx: int
    _section_idx: int

    # 撰写
    sections: dict[str, str]
    section_order: list[str]
    current_section_idx: int

    # 图表凡例
    appendix_data: dict

    # 审校
    review_results: list[dict]
    quality_score: float
    quality_checks: list[dict]

    # 引用
    references: list[dict]

    # 工作流控制
    iteration_count: int
    max_iterations: int
    errors: list[str]

    # 总体报告（累计流程日志 + 审计日志）
    report: str

    # SSE 事件队列
    pending_events: list[dict]
