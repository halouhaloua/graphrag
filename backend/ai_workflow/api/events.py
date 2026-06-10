"""工作流事件类型常量"""


class WorkflowEventType:
    """工作流执行过程中的 SSE 事件类型"""

    WORKFLOW_START = "workflow_start"
    WORKFLOW_COMPLETE = "workflow_complete"
    WORKFLOW_ERROR = "workflow_error"
    NODE_START = "node_start"
    NODE_COMPLETE = "node_complete"
    NODE_ERROR = "node_error"
    NODE_OUTPUT = "node_output"

    # 团队执行事件
    TEAM_START = "team_start"
    TEAM_HANDOFF = "team_handoff"
    TEAM_ROLE_START = "team_role_start"
    TEAM_ROLE_COMPLETE = "team_role_complete"
