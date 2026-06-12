import asyncio
import json
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_workflow.conversation.model import WorkflowConversation
from ai_workflow.workflow.model import WorkflowDef, WorkflowInstance
from ai_workflow.workflow.service import WorkflowEngine

logger = logging.getLogger(__name__)


class ConversationService:
    """对话会话服务

    管理多轮对话的生命周期：创建会话、加载历史、注入上下文、执行 turn。
    """

    @staticmethod
    async def create_conversation(
        workflow_def_id: str,
        user_id: str,
        db: AsyncSession,
    ) -> WorkflowConversation:
        """创建新会话"""
        conv = WorkflowConversation(
            workflow_def_id=workflow_def_id,
            sys_creator_id=user_id,
        )
        db.add(conv)
        await db.commit()
        await db.refresh(conv)
        return conv

    @staticmethod
    async def load_chat_history(
        conversation_id: str,
        db: AsyncSession,
    ) -> list[dict]:
        """加载会话历史，返回 ``[{role, content}]`` 格式

        从该会话已完成的历史 instance 中提取用户输入和 AI 回复。
        """
        result = await db.execute(
            select(WorkflowInstance)
            .where(
                WorkflowInstance.conversation_id == conversation_id,
                WorkflowInstance.is_deleted == False,  # noqa: E712
                WorkflowInstance.status == "completed",
            )
            .order_by(WorkflowInstance.turn_index)
        )
        instances = result.scalars().all()

        history: list[dict] = []
        for inst in instances:
            try:
                inp = (
                    json.loads(inst.input_params)
                    if isinstance(inst.input_params, str)
                    else (inst.input_params or {})
                )
                out = (
                    json.loads(inst.output_result)
                    if isinstance(inst.output_result, str)
                    else (inst.output_result or {})
                )
            except (json.JSONDecodeError, TypeError):
                continue

            user_msg = inp.get("message", "") if isinstance(inp, dict) else ""

            # 从 end-1 节点提取 AI 回复（end-1 的 result 即主节点的输出文本）
            ai_reply = ""
            if isinstance(out, dict):
                end_result = out.get("end-1")
                if isinstance(end_result, str):
                    ai_reply = end_result
            if user_msg:
                history.append({"role": "user", "content": user_msg})
            if ai_reply:
                history.append({"role": "assistant", "content": ai_reply})

        return history

    @staticmethod
    async def inject_history_into_nodes(
        wf_def: WorkflowDef,
        history: list[dict],
    ) -> str:
        """将对话历史注入工作流中 chat 节点的 ``_history`` 参数

        返回修改后的 nodes JSON 字符串。
        """
        nodes = json.loads(wf_def.nodes)
        for node in nodes:
            if node.get("type") == "chat":
                node.setdefault("params", {})["_history"] = history
        return json.dumps(nodes, ensure_ascii=False)

    @staticmethod
    async def execute_turn(
        conversation_id: str,
        message: str,
        db: AsyncSession,
        user_id: str,
        stream_queue: Optional[asyncio.Queue] = None,
    ) -> tuple[WorkflowInstance, Optional[str]]:
        """准备一轮对话的执行

        1. 加载会话和工作流定义
        2. 加载历史对话
        3. 创建 WorkflowInstance
        4. 临时注入 history 到 chat 节点（调用方需在引擎执行后恢复节点）

        Returns:
            tuple: (instance, original_nodes) — 调用方需在引擎执行后将 ``original_nodes``
            写回工作流定义
        """
        conv = await db.get(WorkflowConversation, conversation_id)
        if not conv or conv.is_deleted:
            raise ValueError("会话不存在")

        wf_def = await db.get(WorkflowDef, conv.workflow_def_id)
        if not wf_def or wf_def.is_deleted:
            raise ValueError("工作流定义不存在")

        history = await ConversationService.load_chat_history(conversation_id, db)
        turn_index = len(history) // 2 + 1

        # 创建工作流实例
        instance = await WorkflowEngine.create_instance(
            conv.workflow_def_id,
            {"message": message, "chat_history": history},
            user_id,
            db,
        )
        instance.conversation_id = conversation_id
        instance.turn_index = turn_index
        await db.commit()

        # 注入 history 到 chat 节点（临时修改）
        original_nodes: Optional[str] = None
        if history:
            original_nodes = wf_def.nodes
            wf_def.nodes = await ConversationService.inject_history_into_nodes(
                wf_def, history
            )
            await db.commit()

        # 首次对话自动生成标题
        if not conv.title and turn_index == 1:
            conv.title = message[:80]
            await db.commit()

        await db.refresh(instance)
        return instance, original_nodes
