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

    from ai_workflow.nodes import (
        api_call,
        arxiv_search,
        browser_agent,
        chat,
        python_execute,
        serper_scrape,
        serper_search,
        weather_forecast,
    )

    _ = (
        api_call,
        arxiv_search,
        browser_agent,
        chat,
        python_execute,
        serper_scrape,
        serper_search,
        weather_forecast,
    )
