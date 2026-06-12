from fastapi import APIRouter

from ai_workflow.workflow.api import router as api_router
from ai_workflow.team.api import router as team_router
from ai_workflow.conversation.api import router as conversation_router

router = APIRouter()
router.include_router(api_router)
router.include_router(team_router)
router.include_router(conversation_router)
