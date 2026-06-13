import asyncio
import concurrent.futures
from loguru import logger
import os
import platform
from functools import partial
from typing import Any, Dict

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from browser_use import Agent
from browser_use import Browser
from browser_use import ChatOpenAI as BrowserChatOpenAI

from ai_workflow.nodes.base import BaseNode, NodeContext
from ai_workflow.nodes.registry import register_node

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())




@register_node(
    "browser_agent",
    metadata={
        "name": "浏览器自动化",
        "description": "使用浏览器自动执行网页操作任务",
        "params": {
            "task": {
                "type": "str",
                "required": True,
                "description": "要执行的浏览器任务描述",
            },
        },
        "output": {"result": "任务执行结果"},
    },
)
class BrowserAgentNode(BaseNode):
    """浏览器自动化节点 - 使用 browser-use 驱动真实浏览器执行任务"""

    def __init__(self):
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=int(os.getenv("BROWSER_AGENT_THREADS", "4"))
        )

    async def _run_in_thread(self, func, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, partial(func, *args, **kwargs)
        )

    async def execute(
        self, params: Dict[str, Any], context: NodeContext
    ) -> Dict[str, Any]:
        task = str(params.get("task", ""))
        if not task:
            raise ValueError("task参数不能为空")

        browser = None
        try:
            executable_path = params.get(
                "executable_path",
                os.getenv("BROWSER_EXECUTABLE_PATH", ""),
            )
            user_data_dir = params.get(
                "user_data_dir",
                os.getenv("BROWSER_USER_DATA_DIR", ""),
            )
            chrome_kwargs = {}
            if executable_path:
                chrome_kwargs["executable_path"] = executable_path
            if user_data_dir:
                chrome_kwargs["user_data_dir"] = user_data_dir
                chrome_kwargs["profile_directory"] = params.get(
                    "profile_directory",
                    os.getenv("BROWSER_PROFILE_DIRECTORY", "Default"),
                )

            browser = (
                await self._run_in_thread(Browser, **chrome_kwargs)
                if chrome_kwargs
                else await self._run_in_thread(Browser)
            )

            llm_model = params.get(
                "llm_model", os.getenv("BROWSER_USE_MODEL", "gpt-4o")
            )
            llm = BrowserChatOpenAI(
                model=llm_model,
                base_url=os.getenv("BROWSER_BASE_URL", ""),
                api_key=os.getenv("BROWSER_USE_API_KEY", ""),
                temperature=0.0,
            )

            agent = Agent(
                task=task,
                llm=llm,
                browser=browser,
                save_conversation_path=os.getenv("BROWSER_SAVE_CONVERSATION_PATH", ""),
                generate_gif=os.getenv("BROWSER_GENERATE_GIF", "false").lower()
                == "true",
            )
            result = await agent.run()

            analysis_prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "你是一个智能问答助手，请只参考context内容回答task问题，不要发散，只输出答案。",
                    ),
                    ("human", "task：{task}\n\ncontext：{result}"),
                ]
            )
            chain = analysis_prompt | llm | StrOutputParser()
            analysis = await chain.ainvoke({"task": task, "result": result})

            return {"success": True, "result": analysis}

        except Exception as e:
            logger.error(f"浏览器任务失败: {e}", exc_info=True)
            return {"success": False, "error": str(e), "result": None}

        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass

    async def close(self):
        self._executor.shutdown(wait=True)
