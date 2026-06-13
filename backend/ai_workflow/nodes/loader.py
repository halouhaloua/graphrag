"""节点与工具加载器

在应用启动或测试初始化时调用 ``load_all_nodes()`` 触发所有 ``@register_node`` 装饰器。
"""

_loaded = False


def load_all_nodes():
    """导入所有节点和工具模块，触发 @register_node 装饰器注册"""
    global _loaded
    if _loaded:
        return
    _loaded = True

    # ── 流程控制节点（nodes/） ─────────────────────────────────
    import ai_workflow.nodes._start  # noqa: F401
    import ai_workflow.nodes._end  # noqa: F401
    import ai_workflow.nodes.chat  # noqa: F401

    # ── 工具类节点（tools/） ──────────────────────────────────
    import ai_workflow.tools.api_call  # noqa: F401
    import ai_workflow.tools.arxiv_search  # noqa: F401
    import ai_workflow.tools.browser_agent  # noqa: F401
    import ai_workflow.tools.python_execute  # noqa: F401
    import ai_workflow.tools.rag_query  # noqa: F401
    import ai_workflow.tools.serper_search  # noqa: F401
    import ai_workflow.tools.web_crawler  # noqa: F401
    import ai_workflow.tools.weather_forecast  # noqa: F401

    # ── 条件 + 数据库查询 ──────────────────────────────────────
    import ai_workflow.tools.condition  # noqa: F401
    import ai_workflow.tools.db_query  # noqa: F401


def reset_loaded():
    """重置加载状态（用于测试）"""
    global _loaded
    _loaded = False
