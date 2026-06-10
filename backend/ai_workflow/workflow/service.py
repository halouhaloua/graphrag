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

_running_tasks: dict[str, asyncio.Task] = {}


class WorkflowEngine:
    """基于 DAG 的工作流执行引擎

    提供工作流定义的拓扑排序验证、变量引用解析、
    工作流实例创建和异步执行等核心功能。

    .. code-block:: python

        engine = WorkflowEngine()
        ok, err, levels = engine.validate_dag(nodes, edges)
        if ok:
            inst = await engine.create_instance(def_id, {}, user_id, db)
            await engine.execute_instance(inst.id, db)
    """

    # ── 运行中任务注册 ────────────────────────────────

    @staticmethod
    def register_running_task(instance_id: str, task: asyncio.Task):
        _running_tasks[instance_id] = task

    @staticmethod
    def cancel_running_task(instance_id: str):
        task = _running_tasks.pop(instance_id, None)
        if task and not task.done():
            task.cancel()

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
                WorkflowDef.is_deleted == False,  # noqa: E712
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

        按拓扑排序结果逐层执行节点，同层节点使用独立 DB session 并行运行。
        支持通过 ``stream_queue`` 推送 SSE 事件。

        Args:
            instance_id (`str`):
                工作流实例 ID
            db (`AsyncSession`):
                数据库会话（用于实例状态更新）
            stream_queue (`asyncio.Queue | None`, optional):
                用于推送 SSE 事件的异步队列
        """
        from app.config import settings

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

        try:
            for level in levels:
                if cancel:
                    for nid in level:
                        await WorkflowEngine._log_cancelled_node(nid, instance_id)
                    continue

                tasks = [
                    WorkflowEngine._execute_single_node(
                        nid,
                        node_map[nid],
                        instance_id,
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

        except Exception as e:
            instance.status = "failed"
            instance.error = str(e)
            raise

        finally:
            if instance.status == "running":
                instance.status = "failed"
                instance.error = "执行异常终止"
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
                {"instance_id": instance_id, "error": instance.error},
            )
        else:
            await WorkflowEngine._push_event(
                stream_queue,
                WorkflowEventType.WORKFLOW_COMPLETE,
                {"instance_id": instance_id, "status": instance.status},
            )

    # ── 单节点执行（独立 DB session）──────────────────

    @staticmethod
    async def _execute_single_node(
        node_id: str,
        node_def: dict,
        instance_id: str,
        node_outputs: dict[str, dict],
        stream_queue: Optional[asyncio.Queue],
        settings: Any,
    ) -> dict:
        """执行单个工作流节点（使用独立 DB session）

        每个节点执行时创建独立的 ``AsyncSession``，避免同层并发时的 session 竞争。

        Args:
            node_id (`str`): 节点 ID
            node_def (`dict`): 节点定义
            instance_id (`str`): 工作流实例 ID
            node_outputs (`dict[str, dict]`): 已完成节点的输出
            stream_queue (`asyncio.Queue | None`): SSE 事件推送队列
            settings (`Any`): 应用配置对象

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

        node_timeout = float(node_def.get("params", {}).get("_timeout", 3600))

        async with _async_session() as task_db:
            node_log = WorkflowNodeLog(
                instance_id=instance_id,
                node_id=node_id,
                node_type=node_type,
                status="running",
                input_data=json.dumps(resolved_params, ensure_ascii=False),
                started_at=datetime.now(),
            )
            task_db.add(node_log)
            await task_db.commit()
            await task_db.refresh(node_log)

            await WorkflowEngine._push_event(
                stream_queue,
                WorkflowEventType.NODE_START,
                {"node_id": node_id, "node_type": node_type},
            )

            start = time.time()
            try:
                node: BaseNode = node_cls()
                context = NodeContext(
                    db=task_db,
                    settings=settings,
                    logger=logger,
                    node_id=node_id,
                    instance_id=instance_id,
                    stream_queue=stream_queue,
                )
                result = await asyncio.wait_for(
                    node.execute(resolved_params, context),
                    timeout=node_timeout,
                )

                duration = int((time.time() - start) * 1000)
                node_log.status = "completed"
                node_log.output_data = json.dumps(result, ensure_ascii=False)
                node_log.duration_ms = duration
                node_log.finished_at = datetime.now()
                await task_db.commit()

                await WorkflowEngine._push_event(
                    stream_queue,
                    WorkflowEventType.NODE_COMPLETE,
                    {"node_id": node_id, "duration_ms": duration},
                )
                return result

            except asyncio.TimeoutError:
                duration = int((time.time() - start) * 1000)
                node_log.status = "failed"
                node_log.error = f"节点执行超时 ({node_timeout}s)"
                node_log.duration_ms = duration
                node_log.finished_at = datetime.now()
                await task_db.commit()
                raise TimeoutError(f"节点 {node_id} 执行超时 ({node_timeout}s)")

            except Exception as e:
                duration = int((time.time() - start) * 1000)
                node_log.status = "failed"
                node_log.error = str(e)
                node_log.duration_ms = duration
                node_log.finished_at = datetime.now()
                await task_db.commit()

                await WorkflowEngine._push_event(
                    stream_queue,
                    WorkflowEventType.NODE_ERROR,
                    {"node_id": node_id, "error": str(e), "duration_ms": duration},
                )
                raise

    # ── 辅助方法 ──────────────────────────────────────

    @staticmethod
    async def _log_cancelled_node(node_id: str, instance_id: str):
        """记录被取消的节点日志（使用独立 DB session）"""
        async with _async_session() as task_db:
            log = WorkflowNodeLog(
                instance_id=instance_id,
                node_id=node_id,
                node_type="",
                status="cancelled",
                started_at=datetime.now(),
                finished_at=datetime.now(),
            )
            task_db.add(log)
            await task_db.commit()

    @staticmethod
    async def _push_event(
        queue: Optional[asyncio.Queue],
        event: str,
        data: dict,
    ):
        """向 SSE 流推送事件"""
        if queue is None:
            return
        await queue.put(
            {
                "event": event,
                "data": json.dumps(data, ensure_ascii=False),
            }
        )


def _async_session():
    """获取异步 DB session 上下文管理器"""
    from app.database import AsyncSessionLocal

    return AsyncSessionLocal()
