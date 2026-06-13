"""数据库查询节点

在工作流中执行 SQL SELECT 查询，返回结构化的结果集。
**仅支持只读查询**，拒绝 INSERT/UPDATE/DELETE/DDL 等写操作。
"""

import json
from loguru import logger
import re
from typing import Any, Dict

from sqlalchemy import text

from ai_workflow.nodes.base import BaseNode, NodeContext
from ai_workflow.nodes.registry import register_node


# 安全的 SQL 开头关键字
_SAFE_PREFIXES = re.compile(
    r"^\s*(SELECT|WITH|EXPLAIN|DESCRIBE|SHOW|PRAGMA)\b",
    re.IGNORECASE,
)

# 拒绝的关键字（包含在 SQL 中且非注释）
_BLOCKED_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|EXECUTE)\b",
    re.IGNORECASE,
)


@register_node(
    "db_query",
    metadata={
        "name": "数据库查询",
        "description": "执行 SQL SELECT 查询，返回结果集",
        "params": {
            "sql": {
                "type": "str",
                "required": True,
                "description": "SQL SELECT 查询语句",
            },
            "params": {
                "type": "dict",
                "default": {},
                "description": "参数化查询参数 {key: value}，SQL 中用 :key 引用",
            },
            "max_rows": {
                "type": "int",
                "default": 100,
                "description": "最大返回行数",
            },
        },
        "output": {
            "result": "查询结果 JSON 数组",
            "columns": "列名列表",
            "row_count": "行数",
            "success": "是否成功",
        },
    },
)
class DbQueryNode(BaseNode):
    """数据库查询节点

    使用 ``NodeContext.db`` 执行 SQL SELECT 查询，支持参数化查询。
    仅允许只读操作。

    Usage in DAG::

        params:
          sql: "SELECT id, name FROM users WHERE dept = :dept AND age > :min_age LIMIT :limit"
          params:
            dept: engineering
            min_age: 25
            limit: 10
    """

    async def execute(
        self, params: Dict[str, Any], context: NodeContext
    ) -> Dict[str, Any]:
        sql = str(params.get("sql", "")).strip()
        if not sql:
            raise ValueError("sql 参数不能为空")

        query_params = params.get("params", {})
        if isinstance(query_params, str):
            query_params = json.loads(query_params)
        if not isinstance(query_params, dict):
            raise ValueError("params 参数必须是字典类型")

        max_rows = min(int(params.get("max_rows", 100)), 1000)

        # ── 安全检查 ───────────────────────────────────────────
        if not _SAFE_PREFIXES.match(sql):
            return {
                "result": [],
                "columns": [],
                "row_count": 0,
                "success": False,
                "error": "仅允许 SELECT / WITH / EXPLAIN / SHOW 等只读查询",
            }

        # 排除注释中的关键字误报，检查有效 SQL
        clean_sql = _remove_sql_comments(sql)
        if _BLOCKED_KEYWORDS.search(clean_sql):
            return {
                "result": [],
                "columns": [],
                "row_count": 0,
                "success": False,
                "error": "查询包含被拒绝的写操作关键字",
            }

        # ── 执行查询 ───────────────────────────────────────────
        db = context.db
        try:
            stmt = text(sql)
            result = await db.execute(stmt, query_params)
            rows = result.fetchmany(max_rows)
            columns = list(result.keys()) if result.keys() else []
            serialized = [dict(zip(columns, row)) for row in rows]

            return {
                "result": json.dumps(serialized, ensure_ascii=False, default=str),
                "columns": columns,
                "row_count": len(serialized),
                "success": True,
            }

        except Exception as e:
            error_msg = str(e)
            # 不暴露 SQL 内部细节到前端
            logger.error("数据库查询失败: %s | SQL: %s | params: %s", error_msg, sql, query_params)
            return {
                "result": [],
                "columns": [],
                "row_count": 0,
                "success": False,
                "error": f"查询执行失败: {type(e).__name__}",
            }


def _remove_sql_comments(sql: str) -> str:
    """移除 SQL 中的单行注释（--）和多行注释（/* */）

    简化实现：假设 SQL 不包含字符串字面量中的注释标记。
    """
    # 移除多行注释 /* ... */
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    # 移除单行注释 --（到行尾）
    lines = sql.split("\n")
    cleaned = []
    for line in lines:
        # 不在简单引号保护中时移除 -- 后的内容
        in_single = False
        in_double = False
        pos = -1
        for i, ch in enumerate(line):
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
            elif ch == "-" and i + 1 < len(line) and line[i + 1] == "-":
                if not in_single and not in_double:
                    pos = i
                    break
        cleaned.append(line[:pos] if pos >= 0 else line)
    return "\n".join(cleaned)
