from typing import TypedDict, Optional


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

    # 研究产出
    research_data: dict
    global_facts: list[dict]

    # 史料考证
    verified_data: dict
    contradictions: list[dict]
    human_decision: Optional[dict]

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

    # SSE 事件队列
    pending_events: list[dict]
