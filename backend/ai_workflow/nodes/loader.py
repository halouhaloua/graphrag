"""节点模块加载器

在应用启动或测试初始化时调用 ``load_all_nodes()`` 触发所有 ``@register_node`` 装饰器。
"""

import logging

logger = logging.getLogger(__name__)

_loaded = False


def load_all_nodes():
    """导入所有节点模块，触发 @register_node 装饰器注册"""
    global _loaded
    if _loaded:
        return
    _loaded = True

    import ai_workflow.nodes._start  # noqa: F401
    import ai_workflow.nodes._end  # noqa: F401
    import ai_workflow.nodes.api_call  # noqa: F401
    import ai_workflow.nodes.arxiv_search  # noqa: F401
    import ai_workflow.nodes.browser_agent  # noqa: F401
    import ai_workflow.nodes.chat  # noqa: F401
    import ai_workflow.nodes.python_execute  # noqa: F401
    import ai_workflow.nodes.serper_scrape  # noqa: F401
    import ai_workflow.nodes.serper_search  # noqa: F401
    import ai_workflow.nodes.weather_forecast  # noqa: F401


def reset_loaded():
    """重置加载状态（用于测试）"""
    global _loaded
    _loaded = False
