from agentscope.agent import Agent
from agentscope.model import OpenAIChatModel
from agentscope.credential import OpenAICredential
from agentscope.tool import Toolkit
from agentscope.skill import LocalSkillLoader
from agentscope.agent import ContextConfig

from app.config import settings
from chronicle_writer.config import get_chronicle_config
from chronicle_writer.agents.prompts import (
    COORDINATOR_PROMPT,
    RESEARCHER_PROMPT,
    DRAFTER_PROMPT,
    REVIEWER_PROMPT,
    MAIN_AGENT_PROMPT,
    RELEVANCE_FILTER_PROMPT,
)
from chronicle_writer.tools import (
    RAGSearchTool,
    VerifyFactTool,
    ChronicleWriteTool,
    SectionCRUDTool,
    add_reference_tool,
    template_tool,
    outline_tool,
)


_shared_model = None


def _get_model():
    global _shared_model
    if _shared_model is None:
        _shared_model = OpenAIChatModel(
            credential=OpenAICredential(
                api_key=settings.LLM_API_KEY,
                base_url=settings.LLM_BASE_URL,
            ),
            model=settings.LLM_MODEL,
        )
    return _shared_model


def _get_context_config():
    return ContextConfig(
        trigger_ratio=0.7,
        reserve_ratio=0.2,
        tool_result_limit=3000,
    )


def _get_skills_loader():
    cfg = get_chronicle_config()
    return LocalSkillLoader(
        directory=cfg.skills_dir,
        scan_subdir=True,
    )


def create_coordinator() -> Agent:
    """创建主编协调智能体"""
    return Agent(
        name="coordinator",
        system_prompt=COORDINATOR_PROMPT,
        model=_get_model(),
        toolkit=Toolkit(
            tools=[
                SectionCRUDTool(),
                template_tool,
                outline_tool,
            ],
            skills_or_loaders=[_get_skills_loader()],
        ),
        context_config=_get_context_config(),
    )


def create_researcher() -> Agent:
    """创建研究智能体（资料采集+史料考证）"""
    return Agent(
        name="researcher",
        system_prompt=RESEARCHER_PROMPT,
        model=_get_model(),
        toolkit=Toolkit(
            tools=[
                RAGSearchTool(),
                VerifyFactTool(),
            ],
            skills_or_loaders=[_get_skills_loader()],
        ),
        context_config=_get_context_config(),
    )


def create_drafter() -> Agent:
    """创建撰稿智能体（条目撰写+图表凡例）"""
    return Agent(
        name="drafter",
        system_prompt=DRAFTER_PROMPT,
        model=_get_model(),
        toolkit=Toolkit(
            tools=[
                RAGSearchTool(),
                SectionCRUDTool(),
                add_reference_tool,
            ],
            skills_or_loaders=[_get_skills_loader()],
        ),
        context_config=_get_context_config(),
    )


def create_reviewer() -> Agent:
    """创建审校智能体（校审核对+质检）"""
    return Agent(
        name="reviewer",
        system_prompt=REVIEWER_PROMPT,
        model=_get_model(),
        toolkit=Toolkit(
            tools=[
                RAGSearchTool(),
                VerifyFactTool(),
            ],
            skills_or_loaders=[_get_skills_loader()],
        ),
        context_config=_get_context_config(),
    )


# ─── 已弃用：引文管理智能体（由 create_relevance_filter 替代） ───
# def create_citation_agent() -> Agent:
#     """创建引用管理智能体"""
#     return Agent(
#         name="citation",
#         system_prompt=CITATION_PROMPT,
#         model=_get_model(),
#         toolkit=Toolkit(
#             tools=[
#                 add_reference_tool,
#             ],
#             skills_or_loaders=[_get_skills_loader()],
#         ),
#         context_config=_get_context_config(),
#     )


def create_relevance_filter() -> Agent:
    """创建相关度审校智能体"""
    return Agent(
        name="relevance_filter",
        system_prompt=RELEVANCE_FILTER_PROMPT,
        model=_get_model(),
        toolkit=Toolkit(skills_or_loaders=[_get_skills_loader()]),
        context_config=_get_context_config(),
    )


def create_main_agent() -> Agent:
    """创建主智能体（对话 + 图谱搜索 + 志书写作）"""
    return Agent(
        name="chronicle_writer",
        system_prompt=MAIN_AGENT_PROMPT,
        model=_get_model(),
        toolkit=Toolkit(
            tools=[
                RAGSearchTool(),
                VerifyFactTool(),
                ChronicleWriteTool(),
            ],
            skills_or_loaders=[_get_skills_loader()],
        ),
        context_config=_get_context_config(),
    )
