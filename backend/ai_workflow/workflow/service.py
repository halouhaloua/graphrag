import asyncio
import json
import logging
import re
import time
from collections import deque
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_workflow.workflow.events import WorkflowEventType
from ai_workflow.workflow.model import WorkflowDef, WorkflowInstance, WorkflowNodeLog
from ai_workflow.nodes.base import BaseNode, NodeContext
from ai_workflow.nodes.registry import NodeRegistry

logger = logging.getLogger(__name__)

_REF_PATTERN = re.compile(r"\$\{(\w+)\.(\w+)\}")


class WorkflowEngine:
    """基于 DAG 的工作流执行引擎

    提供工作流定义的拓扑排序验证、变量引用解析、
    工作流实例创建和异步执行等核心功能。

    .. code-block:: python

        # 使用示例
        engine = WorkflowEngine()
        ok, err, levels = engine.validate_dag(nodes, edges)
        if ok:
            inst = await engine.create_instance(def_id, {}, user_id, db)
            await engine.execute_instance(inst.id, db)
    """

    # ── 拓扑排序 ──────────────────────────────────────

    @staticmethod
    def validate_dag(
        nodes: list[dict], edges: list[dict]
    ) -> tuple[bool, str, list[list[str]]]:
        """验证工作流是否构成有向无环图（DAG），返回按层级分组的执行顺序

        Args:
            nodes (`list[dict]`):
                节点列表，每项包含 ``id``, ``type``, ``params`` 等字段
            edges (`list[dict]`):
                边列表，每项包含 ``source``, ``target`` 字段

        Returns:
            `tuple[bool, str, list[list[str]]]`:
                第一项——是否有效 DAG
                第二项——错误信息（有效时为空字符串）
                第三项——按执行顺序分层的节点 ID 列表（每层内可并行执行）
        """
        node_ids = {n["id"] for n in nodes}
        if not node_ids:
            return True, "", []

        adj: dict[str, list[str]] = {nid: [] for nid in node_ids}
        in_deg: dict[str, int] = {nid: 0 for nid in node_ids}

        for edge in edges:
            src = edge.get("source")
            tgt = edge.get("target")
            if src not in node_ids:
                logger.warning("边引用不存在的源节点: %s，已跳过", src)
                continue
            if tgt not in node_ids:
                logger.warning("边引用不存在的目标节点: %s，已跳过", tgt)
                continue
            adj[src].append(tgt)
            in_deg[tgt] = in_deg.get(tgt, 0) + 1

        queue = deque(nid for nid in node_ids if in_deg[nid] == 0)
        if not queue:
            return False, "工作流包含循环依赖（所有节点均有入边）", []

        levels: list[list[str]] = []
        visited = 0

        while queue:
            level: list[str] = []
            for _ in range(len(queue)):
                nid = queue.popleft()
                level.append(nid)
                visited += 1
                for nb in adj[nid]:
                    in_deg[nb] -= 1
                    if in_deg[nb] == 0:
                        queue.append(nb)
            levels.append(level)

        if visited != len(node_ids):
            return False, "工作流包含循环依赖", []

        return True, "", levels

    # ── 变量引用解析 ──────────────────────────────────

    @staticmethod
    def resolve_params(params: dict, node_outputs: dict[str, dict]) -> dict:
        """解析节点参数中的变量引用

        支持 ``\\${node_id.key}`` 语法引用上游节点的输出。
        引用不存在的节点或键时保持原样不做替换。

        Args:
            params (`dict`):
                原始参数字典
            node_outputs (`dict[str, dict]`):
                已完成节点的输出字典，键为节点 ID，值为该节点的输出数据

        Returns:
            `dict`: 解析后的参数字典
        """

        def _resolve_value(value: Any) -> Any:
            if isinstance(value, str):

                def _replacer(m: re.Match) -> str:
                    nid, key = m.group(1), m.group(2)
                    out = node_outputs.get(nid, {})
                    return str(out.get(key, m.group(0)))

                return _REF_PATTERN.sub(_replacer, value)
            if isinstance(value, dict):
                return {k: _resolve_value(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_resolve_value(v) for v in value]
            return value

        return {k: _resolve_value(v) for k, v in params.items()}

    # ── 创建工作流实例 ────────────────────────────────

    @staticmethod
    async def create_instance(
        def_id: str,
        input_params: Optional[dict],
        user_id: Optional[str],
        db: AsyncSession,
    ) -> WorkflowInstance:
        """创建工作流运行实例

        Args:
            def_id (`str`):
                工作流定义 ID
            input_params (`dict | None`):
                输入参数
            user_id (`str | None`):
                创建人 ID
            db (`AsyncSession`):
                数据库会话

        Returns:
            `WorkflowInstance`: 创建后的运行实例

        Raises:
            `ValueError`: 工作流不存在或未发布
        """
        result = await db.execute(
            select(WorkflowDef).where(
                WorkflowDef.id == def_id,
                not WorkflowDef.is_deleted,
            )
        )
        wf_def = result.scalar_one_or_none()
        if not wf_def:
            raise ValueError(f"工作流不存在: {def_id}")
        if not wf_def.is_published:
            raise ValueError(f"工作流未发布: {wf_def.name}")

        instance = WorkflowInstance(
            workflow_def_id=def_id,
            status="pending",
            input_params=json.dumps(input_params, ensure_ascii=False)
            if input_params
            else None,
            sys_creator_id=user_id,
        )
        db.add(instance)
        await db.commit()
        await db.refresh(instance)
        return instance

    # ── 执行工作流 ────────────────────────────────────

    @staticmethod
    async def execute_instance(
        instance_id: str,
        db: AsyncSession,
        stream_queue: Optional[asyncio.Queue] = None,
    ):
        """执行工作流实例

        按拓扑排序结果逐层执行节点，同层节点并行运行。
        支持通过 ``stream_queue`` 推送 SSE 事件。

        Args:
            instance_id (`str`):
                工作流实例 ID
            db (`AsyncSession`):
                数据库会话
            stream_queue (`asyncio.Queue | None`, optional):
                用于推送 SSE 事件的异步队列
        """
        from app.config import settings  # 延迟导入，避免循环依赖

        instance = await db.get(WorkflowInstance, instance_id)
        if not instance:
            raise ValueError(f"工作流实例不存在: {instance_id}")

        wf_def = await db.get(WorkflowDef, instance.workflow_def_id)
        if not wf_def:
            raise ValueError(f"工作流定义不存在: {instance.workflow_def_id}")

        nodes: list[dict] = json.loads(wf_def.nodes)
        edges: list[dict] = json.loads(wf_def.edges) if wf_def.edges else []
        node_map: dict[str, dict] = {n["id"]: n for n in nodes}

        ok, err, levels = WorkflowEngine.validate_dag(nodes, edges)
        if not ok:
            instance.status = "failed"
            instance.error = err
            instance.finished_at = datetime.now()
            await db.commit()
            await WorkflowEngine._push_event(
                stream_queue,
                WorkflowEventType.WORKFLOW_ERROR,
                {"instance_id": instance_id, "error": err},
            )
            return

        await WorkflowEngine._push_event(
            stream_queue,
            WorkflowEventType.WORKFLOW_START,
            {
                "instance_id": instance_id,
                "workflow_name": wf_def.name,
                "total_nodes": len(nodes),
                "levels": len(levels),
            },
        )

        instance.status = "running"
        instance.started_at = datetime.now()
        await db.commit()

        node_outputs: dict[str, dict] = {}
        cancel = False

        for level in levels:
            if cancel:
                for nid in level:
                    await WorkflowEngine._log_cancelled_node(
                        nid,
                        instance_id,
                        db,
                    )
                continue

            tasks = [
                WorkflowEngine._execute_single_node(
                    nid,
                    node_map[nid],
                    instance_id,
                    db,
                    node_outputs,
                    stream_queue,
                    settings,
                )
                for nid in level
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for nid, res in zip(level, results):
                if isinstance(res, Exception):
                    node_outputs[nid] = {"error": str(res), "success": False}
                    error_mode = node_map[nid].get("error_mode", "stop")
                    if error_mode == "stop":
                        cancel = True
                        instance.status = "failed"
                        instance.error = f"节点 {nid} 执行失败: {res}"
                elif isinstance(res, dict):
                    node_outputs[nid] = res

        if instance.status != "failed":
            instance.status = "completed"
        instance.finished_at = datetime.now()
        instance.output_result = json.dumps(
            {k: v.get("result", v) for k, v in node_outputs.items()},
            ensure_ascii=False,
        )
        await db.commit()

        if instance.status == "failed":
            await WorkflowEngine._push_event(
                stream_queue,
                WorkflowEventType.WORKFLOW_ERROR,
                {
                    "instance_id": instance_id,
                    "error": instance.error,
                },
            )
        else:
            await WorkflowEngine._push_event(
                stream_queue,
                WorkflowEventType.WORKFLOW_COMPLETE,
                {
                    "instance_id": instance_id,
                    "status": instance.status,
                },
            )

    # ── 单节点执行 ────────────────────────────────────

    @staticmethod
    async def _execute_single_node(
        node_id: str,
        node_def: dict,
        instance_id: str,
        db: AsyncSession,
        node_outputs: dict[str, dict],
        stream_queue: Optional[asyncio.Queue],
        settings: Any,
    ) -> dict:
        """执行单个工作流节点

        Args:
            node_id (`str`):
                节点 ID
            node_def (`dict`):
                节点定义
            instance_id (`str`):
                工作流实例 ID
            db (`AsyncSession`):
                数据库会话
            node_outputs (`dict[str, dict]`):
                已完成节点的输出
            stream_queue (`asyncio.Queue | None`):
                SSE 事件推送队列
            settings (`Any`):
                应用配置对象

        Returns:
            `dict`: 节点执行结果

        Raises:
            `ValueError`: 未知节点类型
            `Exception`: 节点执行过程中的任何异常
        """
        node_type = node_def.get("type", "")
        raw_params = node_def.get("params", {})
        resolved_params = WorkflowEngine.resolve_params(raw_params, node_outputs)

        node_cls = NodeRegistry.get(node_type)
        if not node_cls:
            raise ValueError(f"未知节点类型: {node_type}")

        node_log = WorkflowNodeLog(
            instance_id=instance_id,
            node_id=node_id,
            node_type=node_type,
            status="running",
            input_data=json.dumps(resolved_params, ensure_ascii=False),
            started_at=datetime.now(),
        )
        db.add(node_log)
        await db.commit()
        await db.refresh(node_log)

        await WorkflowEngine._push_event(
            stream_queue,
            WorkflowEventType.NODE_START,
            {
                "node_id": node_id,
                "node_type": node_type,
            },
        )

        start = time.time()
        try:
            node: BaseNode = node_cls()
            context = NodeContext(
                db=db,
                settings=settings,
                logger=logger,
                node_id=node_id,
                instance_id=instance_id,
                stream_queue=stream_queue,
            )
            result = await node.execute(resolved_params, context)

            duration = int((time.time() - start) * 1000)
            node_log.status = "completed"
            node_log.output_data = json.dumps(result, ensure_ascii=False)
            node_log.duration_ms = duration
            node_log.finished_at = datetime.now()
            await db.commit()

            await WorkflowEngine._push_event(
                stream_queue,
                WorkflowEventType.NODE_COMPLETE,
                {
                    "node_id": node_id,
                    "duration_ms": duration,
                },
            )
            return result

        except Exception as e:
            duration = int((time.time() - start) * 1000)
            node_log.status = "failed"
            node_log.error = str(e)
            node_log.duration_ms = duration
            node_log.finished_at = datetime.now()
            await db.commit()

            await WorkflowEngine._push_event(
                stream_queue,
                WorkflowEventType.NODE_ERROR,
                {
                    "node_id": node_id,
                    "error": str(e),
                    "duration_ms": duration,
                },
            )
            raise

    # ── 辅助方法 ──────────────────────────────────────

    @staticmethod
    async def _log_cancelled_node(
        node_id: str,
        instance_id: str,
        db: AsyncSession,
    ):
        """记录被取消的节点日志

        当下游节点因上游失败（``error_mode=stop``）而无需执行时，
        创建一条状态为 ``cancelled`` 的日志记录。

        Args:
            node_id (`str`): 节点 ID
            instance_id (`str`): 工作流实例 ID
            db (`AsyncSession`): 数据库会话
        """
        log = WorkflowNodeLog(
            instance_id=instance_id,
            node_id=node_id,
            node_type="",
            status="cancelled",
            started_at=datetime.now(),
            finished_at=datetime.now(),
        )
        db.add(log)
        await db.commit()

    @staticmethod
    async def _push_event(
        queue: Optional[asyncio.Queue],
        event: str,
        data: dict,
    ):
        """向 SSE 流推送事件

        Args:
            queue (`asyncio.Queue | None`):
                事件队列，为 ``None`` 时静默跳过
            event (`str`):
                事件类型名称
            data (`dict`):
                事件数据
        """
        if queue is None:
            return
        await queue.put(
            {
                "event": event,
                "data": json.dumps(data, ensure_ascii=False),
            }
        )
