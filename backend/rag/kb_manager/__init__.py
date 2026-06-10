from fastapi import APIRouter
from .api import router, perm_router

wrapper = APIRouter()
# perm_router 先注册，使其字面路径优先于 router 的 {kb_id} 通配路径匹配
wrapper.include_router(perm_router)
wrapper.include_router(router)

kb_manager_router = wrapper
