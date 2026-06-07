"""节点文本处理工具

功能：
- 提取节点 name/description 等文本信息
- 格式化节点属性用于展示
- 缓存管理（关联图签名一致性）

数据流：
  get_node_text(graph, node_id) → "name description"
  get_node_properties(graph, node_id) → "[key: value, ...]"
  get_node_chunk_id(graph, node_id) → str | None
  build_triple_text(graph, h, r, t) → "head_text relation tail_text"

缓存 I/O（共享图签名）：
  precompute_node_texts(graph) → node_text_cache dict
    → save_node_text_cache() / load_node_text_cache() → pickle
"""

import os
from typing import Dict, Optional, Set, Tuple

import networkx as nx

from rag.rag_models.retrieval import utils as retriever_utils
from rag.rag_models.retrieval.faiss_index import check_consistency
from loguru import logger

# 节点属性展示时跳过的内部字段
SCHEMA_SKIP_FIELDS = {
    "name", "description", "properties", "label", "chunk id", "level",
    "file_name",
}


# ─── 文本提取 ───


def extract_node_name_and_description(node_data: dict) -> Tuple[str, str]:
    """兼容新旧数据结构的 name/description 提取

    新结构：{"properties": {"name": "...", "description": "..."}}
    旧结构：{"name": "...", "description": "..."}

    Args:
        node_data (`dict`): 图节点的 data 字典

    Returns:
        `Tuple[str, str]`: (name, description)，缺失时为空字符串
    """
    return retriever_utils.extract_node_name_and_description(node_data)


def is_valid_node_text(text: str) -> bool:
    """检查节点文本是否可用于编码

    排除空文本和错误标记文本（如 "[Error"、"[Unknown" 开头）。

    Args:
        text (`str`): 待检查文本

    Returns:
        `bool`: True 表示可编码
    """
    return retriever_utils.is_valid_node_text(text)


def get_node_name(graph: nx.MultiDiGraph, node_id: str) -> str:
    """获取节点显示名称

    Args:
        graph (`nx.MultiDiGraph`): 图对象
        node_id (`str`): 节点 ID

    Returns:
        `str`: 节点名称，缺失时返回 node_id
    """
    node_data = graph.nodes.get(node_id, {})
    props = node_data.get("properties", {})
    return props.get("name", node_id)


def get_node_text(
    graph: nx.MultiDiGraph,
    node_id: str,
    cache: Dict[str, str] = None,
) -> str:
    """获取节点的完整文本表示（name + description）

    优先从 cache 读取，避免重复拼接字符串。

    Args:
        graph (`nx.MultiDiGraph`): 图对象
        node_id (`str`): 节点 ID
        cache (`Dict[str, str]`, optional): 节点文本缓存 {节点ID: 文本}

    Returns:
        `str`: "name description" 格式的文本，缺失时返回 "[Node: node_id]"
    """
    if cache and node_id in cache:
        return cache[node_id]
    if node_id not in graph.nodes:
        return f"[Unknown Node: {node_id}]"
    data = graph.nodes[node_id]
    name, description = extract_node_name_and_description(data)
    result = f"{name} {description}".strip()
    if not result:
        result = f"[Node: {node_id}]"
    if cache is not None:
        cache[node_id] = result
    return result


def get_node_properties(
    graph: nx.MultiDiGraph,
    node_id: str,
    skip_fields: Optional[Set[str]] = None,
) -> str:
    """格式化节点属性用于展示，跳过内部字段

    返回格式："[key: value, key: value, ...]"
    遍历 properties 字典和节点 data 字典的顶层字段，
    跳过 SCHEMA_SKIP_FIELDS 中的内部字段。

    Args:
        graph (`nx.MultiDiGraph`): 图对象
        node_id (`str`): 节点 ID
        skip_fields (`Set[str]`, optional): 跳过的字段集合

    Returns:
        `str`: 格式化属性字符串，如 "[类型: 人物, 朝代: 唐朝]"
    """
    if node_id not in graph.nodes:
        return ""
    skip = skip_fields or SCHEMA_SKIP_FIELDS
    data = graph.nodes[node_id]
    properties = []
    for source in [data.get("properties", {}), data]:
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            if key in skip:
                continue
            value_str = (
                ", ".join(map(str, value)) if isinstance(value, list) else str(value)
            )
            properties.append(f"{key}: {value_str}")
    return f"[{', '.join(properties)}]" if properties else ""


def get_node_chunk_id(graph: nx.MultiDiGraph, node_id: str) -> Optional[str]:
    """获取节点关联的文本块 ID

    兼容新旧数据结构：
      新：node["properties"]["chunk id"]
      旧：node["chunk id"]

    该 chunk id 用于将检索到的实体反向关联回其来源文本块。

    Args:
        graph (`nx.MultiDiGraph`): 图对象
        node_id (`str`): 节点 ID

    Returns:
        `Optional[str]`: chunk ID 字符串，不存在则返回 None
    """
    if node_id not in graph.nodes:
        return None
    data = graph.nodes[node_id]
    if isinstance(data.get("properties"), dict):
        chunk_id = data["properties"].get("chunk id")
        if chunk_id:
            return str(chunk_id)
    chunk_id = data.get("chunk id")
    return str(chunk_id) if chunk_id else None


def get_matching_chunks(
    chunk2id: Dict[str, str],
    chunk_ids: Set[str],
) -> Dict[str, str]:
    """从 chunk2id 映射中筛选出指定 chunk_id 对应的文本

    Args:
        chunk2id (`Dict[str, str]`): {chunk_id: chunk_text}
        chunk_ids (`Set[str]`): 需要筛选的 chunk_id 集合

    Returns:
        `Dict[str, str]`: {chunk_id: chunk_text} 交集子集
    """
    return {cid: chunk2id[cid] for cid in chunk_ids if cid in chunk2id}


# ─── 三元组文本 ───


def build_triple_text(
    graph: nx.MultiDiGraph,
    h: str,
    r: str,
    t: str,
) -> Optional[str]:
    """构建三元组的文本表示，用于编码评分

    格式："头文本 关系 尾文本"

    Args:
        graph (`nx.MultiDiGraph`): 图对象
        h (`str`): 头节点 ID
        r (`str`): 关系名称
        t (`str`): 尾节点 ID

    Returns:
        `Optional[str]`: 三元组文本（头尾均有效时），任一无效则返回 None
    """
    head_text = get_node_text(graph, h)
    tail_text = get_node_text(graph, t)
    if not is_valid_node_text(head_text) or not is_valid_node_text(tail_text):
        return None
    return f"{head_text} {r} {tail_text}"


# ─── 预计算 ───


def precompute_node_texts(graph: nx.MultiDiGraph) -> Dict[str, str]:
    """预计算所有节点的文本并缓存，避免重复编码

    遍历图中所有节点，调用 get_node_text 获取完整文本，
    仅保留有效文本到缓存字典。

    Args:
        graph (`nx.MultiDiGraph`): 图对象

    Returns:
        `Dict[str, str]`: {节点ID: 节点文本}
    """
    cache = {}
    for node in graph.nodes():
        try:
            text = get_node_text(graph, node)
            if is_valid_node_text(text):
                cache[node] = text
        except Exception:
            continue
    return cache


# ─── 缓存 I/O ───


def _text_cache_path(cache_dir: str, dataset: str) -> str:
    """节点文本缓存文件路径

    Args:
        cache_dir (`str`): 缓存根目录
        dataset (`str`): 数据集名称

    Returns:
        `str`: pickle 缓存文件路径
    """
    return os.path.join(cache_dir, dataset, "node_text_cache.pkl")


def load_node_text_cache(
    graph: nx.MultiDiGraph,
    cache_dir: str,
    dataset: str,
) -> Optional[Dict[str, str]]:
    """加载节点文本缓存，校验图签名一致性

    优先从磁盘加载，签名不匹配或缓存缺失时返回 None。

    Args:
        graph (`nx.MultiDiGraph`): 当前图对象（用于签名校验）
        cache_dir (`str`): 缓存根目录
        dataset (`str`): 数据集名称

    Returns:
        `Optional[Dict[str, str]]`: {节点ID: 节点文本}，无效时返回 None
    """
    if not check_consistency(graph, cache_dir, dataset):
        return None
    expected_keys: Set[str] = set(graph.nodes())
    cache = retriever_utils.load_pickle_cache(
        cache_dir,
        dataset,
        "node_text_cache",
        expected_keys=expected_keys,
        logger=logger,
    )
    return cache


def save_node_text_cache(cache: Dict[str, str], cache_dir: str, dataset: str):
    """持久化节点文本缓存

    保存为 pickle 文件，后续通过 load_node_text_cache 加载。

    Args:
        cache (`Dict[str, str]`): {节点ID: 节点文本}
        cache_dir (`str`): 缓存根目录
        dataset (`str`): 数据集名称
    """
    retriever_utils.save_pickle_cache(
        cache,
        cache_dir,
        dataset,
        "node_text_cache",
        logger=logger,
    )
