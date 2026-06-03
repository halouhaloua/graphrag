"""社区操作工具

功能：
- 从社区节点展开其成员实体
- 从检索到的三元组反向收集关联的社区摘要
"""

from typing import Dict, List, Tuple

import networkx as nx


def get_community_nodes(
    graph: nx.MultiDiGraph,
    comm_node_id: str,
    name_to_id: Dict[str, str] = {},
) -> List[str]:
    """获取社区节点包含的所有成员实体 ID

    社区节点的 properties["members"] 中存储了成员名称列表，
    需通过名称反查节点ID（支持 name_to_id 预计算索引加速）
    """
    if comm_node_id not in graph.nodes:
        return []
    if graph.nodes[comm_node_id].get("label") != "community":
        return []
    props = graph.nodes[comm_node_id].get("properties", {})
    member_names = props.get("members", [])
    if not member_names:
        return []
    member_ids = []
    for name in member_names:
        if isinstance(name, list):
            name_str = ", ".join(str(item) for item in name)
        else:
            name_str = str(name).strip()
        if name_to_id and name_str in name_to_id:
            member_ids.append(name_to_id[name_str])
        else:
            # 没有预计算索引时，遍历图查找
            for nid, ndata in graph.nodes(data=True):
                p = ndata.get("properties", {})
                if p.get("name") == name_str:
                    member_ids.append(nid)
                    break
    return member_ids


def collect_community_summaries(
    graph: nx.MultiDiGraph,
    scored_triples: List[Tuple],
) -> List[Dict]:
    """从检索到的三元组收集关联的社区摘要

    遍历三元组中的头尾实体节点，
    沿 member_of 边找到所属社区，
    返回去重后的社区信息（name, description, members, keywords）
    """
    community_set = {}
    for item in scored_triples:
        h, _, t = item[0], item[1], item[2]
        for node_id in (h, t):
            if node_id not in graph.nodes:
                continue
            for _, neighbor, edge_data in graph.out_edges(node_id, data=True):
                if edge_data.get("relation") == "member_of":
                    if neighbor not in community_set:
                        comm_data = graph.nodes.get(neighbor, {})
                        props = comm_data.get("properties", {})
                        community_set[neighbor] = {
                            "name": props.get("name", ""),
                            "description": props.get("description", ""),
                            "members": props.get("members", []),
                            "keywords": props.get("keywords", []),
                        }
    return list(community_set.values())
