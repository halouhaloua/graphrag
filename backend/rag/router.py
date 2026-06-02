# FastAPI imports
from fastapi import APIRouter



# Import routers
from rag.graph_manager.api import router as graph_router
from rag.chat_history.api import router as chat_router
from rag.config.api import router as config_router
from rag.kb_manager import kb_manager_router
from rag.ai_writer.api import router as ai_writer_router
from rag.graph_merge.api import router as graph_merge_router
from rag.utils.call_llm_api import router as llm_router
from rag.file_manager import file_manager_router

router = APIRouter()

# Include routers
router.include_router(graph_router)
router.include_router(file_manager_router)
router.include_router(kb_manager_router)
router.include_router(chat_router)
router.include_router(config_router)
router.include_router(llm_router)
router.include_router(ai_writer_router)
router.include_router(graph_merge_router)