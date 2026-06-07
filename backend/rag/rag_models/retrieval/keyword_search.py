"""关键词搜索模块

功能：
- 使用 jieba 从查询中提取关键词（词性标注 + 专名识别）
- 构建/搜索倒排文本索引（单词 → 节点ID）
- 图路径搜索（DFS 关键词匹配）
- 邻居展开与关系匹配

数据流：
  question → jieba 分词 → extract_query_keywords() → [kw1, kw2, ...]
    → search_by_keywords(text_index, keywords) → 候选节点ID列表
    → path_based_search(graph, candidates, keywords) → DFS 路径三元组
    → get_relation_matched_triples(graph, candidates, relations) → 关系三元组
"""

import os
from typing import Dict, List, Optional, Set, Tuple

import jieba.posseg as pseg
import networkx as nx

from rag.rag_models.retrieval.faiss_index import check_consistency
from rag.rag_models.retrieval.text_processor import get_node_text, is_valid_node_text
from rag.rag_models.retrieval import utils as retriever_utils
from loguru import logger

# jieba 词性 → 关键词类型映射
# nr=人名, ns=地名, nt=机构, nz=专名, nrfg=人名（姓氏+名字）
_NE_POS = {"nr", "ns", "nt", "nz", "nrfg"}
# 所有参与关键词提取的实词词性
_KEY_POS = _NE_POS | {
    "n",
    "nl",
    "vn",
    "an",
    "v",
    "vd",
    "vi",
    "vg",
    "a",
    "ad",
    "eng",
}

# 中文停用词（高频无意义词，避免干扰倒排索引匹配）
_STOP_WORDS = {
    "的",
    "了",
    "在",
    "是",
    "我",
    "有",
    "和",
    "就",
    "不",
    "人",
    "都",
    "一",
    "一个",
    "上",
    "也",
    "很",
    "到",
    "说",
    "要",
    "去",
    "你",
    "会",
    "着",
    "没有",
    "看",
    "好",
    "自己",
    "这",
    "他",
    "她",
    "它",
    "们",
    "什么",
    "那",
    "吗",
    "啊",
    "吧",
    "呢",
    "喔",
    "哦",
    "嘛",
    "呗",
    "呀",
    "及",
    "与",
    "或",
    "但",
    "而",
    "故",
    "其",
    "此",
    "彼",
    "问题",
    "方法",
    "使用",
    "可以",
    "进行",
    "通过",
    "利用",
    "采用",
}


def extract_query_keywords(question: str) -> List[str]:
    """从查询中提取关键词

    使用 jieba 分词 + 词性标注：
    1. 专名词性（nr/ns/nt/nz）→ 等价于 spaCy NER
    2. 常见实词词性（n/v/a 等）→ 等价于 spaCy POS 过滤
    3. eng 词性 → 英文专名（如 Transformer, GPT）

    返回去重后的小写关键词列表
    """
    keywords = []
    words = pseg.lcut(question)
    for word, flag in words:
        word = word.strip().lower()
        if not word or word in _STOP_WORDS:
            continue
        if len(word) <= 1 and flag not in _NE_POS:
            continue
        if flag in _KEY_POS:
            keywords.append(word)
    seen = set()
    unique = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return unique


# ─── 倒排文本索引 ───


def build_node_text_index(
    graph: nx.MultiDiGraph,
    node_text_cache: Dict[str, str],
) -> Dict[str, Set[str]]:
    """构建倒排索引：单词 → 包含该单词的节点ID集合

    从节点文本缓存出发，按空格分词后建索引
    """
    index: Dict[str, Set[str]] = {}
    for node_id, text in node_text_cache.items():
        if not is_valid_node_text(text):
            continue
        for word in text.lower().split():
            word = word.strip(".,;:!?\"'()[]{}")
            if len(word) > 1:
                index.setdefault(word, set()).add(node_id)
    return index


def _text_index_path(cache_dir: str, dataset: str) -> str:
    return os.path.join(cache_dir, dataset, "node_text_index.pkl")


def build_and_save_text_index(
    graph: nx.MultiDiGraph,
    node_text_cache: Dict[str, str],
    cache_dir: str,
    dataset: str,
) -> Dict[str, Set[str]]:
    """构建倒排索引并持久化（set 转为 list 以支持 pickle）"""
    index = build_node_text_index(graph, node_text_cache)
    retriever_utils.save_pickle_cache(
        {k: list(v) for k, v in index.items()},
        cache_dir,
        dataset,
        "node_text_index",
        logger=logger,
    )
    return index


def load_text_index(
    graph: nx.MultiDiGraph,
    cache_dir: str,
    dataset: str,
) -> Optional[Dict[str, Set[str]]]:
    """加载持久化的倒排索引，校验图签名一致性"""
    if not check_consistency(graph, cache_dir, dataset):
        return None
    raw = retriever_utils.load_pickle_cache(
        cache_dir,
        dataset,
        "node_text_index",
        logger=logger,
    )
    if raw is None:
        return None
    return {k: set(v) for k, v in raw.items()}


def save_text_index(index: Dict[str, Set[str]], cache_dir: str, dataset: str):
    """持久化倒排索引"""
    serializable = {k: list(v) for k, v in index.items()}
    retriever_utils.save_pickle_cache(
        serializable,
        cache_dir,
        dataset,
        "node_text_index",
        logger=logger,
    )


def search_by_keywords(
    text_index: Dict[str, Set[str]],
    keywords: List[str],
    top_k: int = 50,
) -> List[str]:
    """通过关键词匹配倒排索引找到候选节点

    对每个关键词，取所有匹配节点的并集
    """
    if not text_index or not keywords:
        return []
    matched = set()
    for kw in keywords:
        if kw in text_index:
            matched.update(text_index[kw])
    matched_list = sorted(matched)
    return matched_list[:top_k]


# ─── 图路径搜索 ───


def path_based_search(
    graph: nx.MultiDiGraph,
    start_nodes: List[str],
    target_keywords: List[str],
    max_depth: int = 2,
) -> List[Tuple[str, str, str]]:
    """DFS 路径搜索：从起始节点出发，在 max_depth 内寻找匹配关键词的路径

    当某邻居节点的文本中包含目标关键词时，记录从起点到该邻居的完整路径三元组
    """
    if not target_keywords:
        return []
    kw_set = {kw.lower() for kw in target_keywords}
    result_triples = []
    visited = set()
    for start in start_nodes:
        if start not in graph.nodes:
            continue
        stack = [(start, 0, [start])]
        while stack:
            current, depth, path = stack.pop()
            if (current, depth) in visited:
                continue
            visited.add((current, depth))
            if depth >= max_depth:
                continue
            for neighbor in graph.neighbors(current):
                edge_data = graph.get_edge_data(current, neighbor)
                if edge_data:
                    rel = list(edge_data.values())[0].get("relation", "")
                    neighbor_text = get_node_text(graph, neighbor).lower()
                    if any(kw in neighbor_text for kw in kw_set):
                        # 记录整条路径上的三元组
                        for i in range(len(path) - 1):
                            u = path[i]
                            v = path[i + 1]
                            e = graph.get_edge_data(u, v)
                            r = list(e.values())[0].get("relation", "") if e else ""
                            result_triples.append((u, r, v))
                        result_triples.append((current, rel, neighbor))
                    stack.append((neighbor, depth + 1, path + [neighbor]))
    return result_triples


# ─── 邻居展开 ───


def get_1hop_triples(
    graph: nx.MultiDiGraph,
    node_ids: List[str],
) -> List[Tuple[str, str, str]]:
    """获取指定节点集合的 1-hop 邻边三元组"""
    node_set = set(node_ids)
    triples = []
    for u, v, data in graph.edges(data=True):
        if u in node_set or v in node_set:
            relation = data.get("relation", "")
            triples.append((u, relation, v))
    return triples


def get_relation_matched_triples(
    graph: nx.MultiDiGraph,
    top_nodes: List[str],
    relations: List[str],
) -> List[Tuple[str, str, str]]:
    """获取同时满足关系类型匹配且端点位于 top_nodes 中的三元组"""
    if not relations:
        return []
    top_set = set(top_nodes)
    rel_set = set(relations)
    results = []
    for u, v, data in graph.edges(data=True):
        rel = data.get("relation", "")
        if rel in rel_set and (u in top_set or v in top_set):
            results.append((u, rel, v))
    return results
