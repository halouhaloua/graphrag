"""DB session factory 和工具初始化（保持 _db_factory + init_tools 供其他模块使用）。"""

_db_factory = None


def init_tools(db_factory):
    global _db_factory
    _db_factory = db_factory
