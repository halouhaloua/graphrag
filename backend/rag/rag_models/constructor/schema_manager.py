"""Schema 管理模块

功能：
- 加载 schema（从 dict 或文件路径）
- 合并 agent 发现的新类型到现有 schema
- 提供默认 schema
- 纯函数，无 DB 依赖
"""

from typing import Any, Dict, List, Optional

DEFAULT_SCHEMA: Dict[str, List[str]] = {
    "Nodes": [
        "person",
        "location",
        "organization",
        "event",
        "object",
        "concept",
        "time_period",
        "creative_work",
        "biological_entity",
        "natural_phenomenon",
    ],
    "Relations": [
        "is_a",
        "part_of",
        "located_in",
        "created_by",
        "used_by",
        "participates_in",
        "related_to",
        "belongs_to",
        "influences",
        "precedes",
        "arrives_in",
        "comparable_to",
    ],
    "Attributes": [
        "name",
        "date",
        "size",
        "type",
        "description",
        "status",
        "quantity",
        "value",
        "position",
        "duration",
        "time",
    ],
}

_KEY_MAP = {
    "nodes": "Nodes",
    "relations": "Relations",
    "attributes": "Attributes",
}


def load_schema(
    schema_path: Optional[str] = None,
    schema_data: Optional[dict] = None,
) -> Dict[str, Any]:
    """加载 schema

    优先级：schema_data > schema_path > {}
    """
    if schema_data is not None:
        return schema_data
    if schema_path:
        try:
            import json

            with open(schema_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    return {}


def merge_schema_types(
    current: Dict[str, List[str]],
    new_types: Dict[str, List[str]],
) -> bool:
    """将 agent 发现的新类型合并到现有 schema

    支持的 key（大小写不敏感）：
    - nodes / Nodes → Nodes 列表
    - relations / Relations → Relations 列表
    - attributes / Attributes → Attributes 列表

    Args:
        current: 当前 schema 字典（会被原地修改）
        new_types: agent 发现的新类型

    Returns:
        True 表示有变更
    """
    updated = False

    for raw_key, new_items in new_types.items():
        if not new_items:
            continue

        target_key = _KEY_MAP.get(raw_key, raw_key)
        existing = current.setdefault(target_key, [])

        for item in new_items:
            if item not in existing:
                existing.append(item)
                updated = True

    return updated
