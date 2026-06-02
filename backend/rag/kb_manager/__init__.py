from fastapi import APIRouter
from .api import router, perm_router

wrapper = APIRouter()
wrapper.include_router(router)
wrapper.include_router(perm_router)

kb_manager_router = wrapper
