"""Schema 类型过滤检索

功能：
- 根据 entity schema_type 过滤候选节点
- 在过滤后的节点集上执行 FAISS 相似度搜索
"""

from typing import Dict, List

import faiss
import numpy as np
import torch

from rag.rag_models.retrieval.faiss_index import FAISSIndexSet


def filter_nodes_by_schema_type(graph, target_types: List[str]) -> List[str]:
    """根据 Schema 类型过滤节点

    只返回 schema_type 匹配目标类型的实体节点，
    无 schema_type 但 label="entity" 的节点也包含（向前兼容）
    """
    if not target_types:
        return list(graph.nodes())
    filtered = []
    for node_id, node_data in graph.nodes(data=True):
        node_properties = node_data.get("properties", {})
        node_schema_type = node_properties.get("schema_type", "")
        if node_schema_type in target_types:
            filtered.append(node_id)
        elif not node_schema_type and node_data.get("label") == "entity":
            filtered.append(node_id)
    return filtered


def similarity_search_on_filtered(
    index_set: FAISSIndexSet,
    query_embed: torch.Tensor,
    filtered_nodes: List[str],
    top_k: int,
) -> Dict:
    """在过滤后的节点集上执行 FAISS 相似度搜索

    通过全局 node_index 中重建过滤后节点的嵌入，
    创建临时 FAISS 索引进行搜索
    """
    if not filtered_nodes:
        return {"top_nodes": []}
    filtered_embeddings = []
    filtered_node_map = {}
    idx = 0
    inv_node_map = {v: k for k, v in index_set.node_map.items()}
    for node_id in filtered_nodes:
        if node_id in inv_node_map:
            orig_idx = inv_node_map[node_id]
            try:
                embed = index_set.node_index.reconstruct(int(orig_idx))
                filtered_embeddings.append(embed)
                filtered_node_map[idx] = node_id
                idx += 1
            except Exception:
                continue
    if not filtered_embeddings:
        return {"top_nodes": filtered_nodes[:top_k]}
    emb_array = np.array(filtered_embeddings).astype("float32")
    temp_index = faiss.IndexFlatIP(emb_array.shape[1])
    temp_index.add(emb_array)
    search_k = min(top_k, len(filtered_embeddings))
    query_np = query_embed.cpu().numpy().reshape(1, -1).astype("float32")
    _, indices = temp_index.search(query_np, search_k)
    top_filtered = [
        filtered_node_map[idx] for idx in indices[0] if idx in filtered_node_map
    ]
    return {"top_nodes": top_filtered}
