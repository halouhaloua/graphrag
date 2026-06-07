"""图谱构建引擎：文档 → 知识图谱。

功能：
- 分块 → LLM 实体/关系/属性提取 → NetworkX 图 → 社区检测 → 格式化输出
- 属性列表自动拼接为实体 description，提升语义检索质量
- 支持 agent 模式下的 Schema 演化（发现新类型自动合并）

数据流：
  documents: [{"title": "...", "text": "..."}]
    → build_knowledge_graph()
    → chunk_text()
      → chunks: ["chunk_text_1", "chunk_text_2"]
      → chunk2id: {"chunk_id": {"chunk": str, "entities": []}}
    → process_level1_level2(chunk)
      → LLM 提取 JSON:
        {
          "attributes": {"实体名": ["属性1", "属性2"]},
          "triples": [["头实体", "关系", "尾实体"]],
          "entity_types": {"实体名": "schema_type"}
        }
      → _process_attributes() → 属性节点 (level=1) + has_attribute 边 + entity_descriptions dict
      → _process_triples() → 实体节点 (level=2) + 关系边
    → triple_deduplicate() → 去重边
    → process_level4() → FastTreeComm 社区检测 → 社区节点 (level=4)
    → format_output()
      → [{start_node: {label, properties}, relation, end_node: {label, properties}}]

节点属性:
  entity:   {name, chunk id, schema_type?, description?, file_name?}
  attribute: {name, chunk id, file_name?}
  community: {name, description, members, keywords, level?}
"""

import json
import os
import threading
import time
from concurrent import futures
from typing import Any, Dict, List, Tuple

import nanoid
import networkx as nx
import tiktoken

try:
    import json_repair

    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False
    json_repair = None

from rag.config import get_config
from rag.rag_models.constructor import tree_comm
from rag.rag_models.constructor.schema_manager import load_schema, merge_schema_types
from rag.rag_models.constructor.text_chunker import chunk_text
from rag.utils import call_llm_api
from loguru import logger


def _validate_triple_format(triple: list) -> tuple | None:
    """校验三元组格式并标准化。

    Args:
        triple (`list`):
            原始三元组，期望至少 3 个元素: [subject, predicate, object]。
            超过 3 个元素时截断为前 3 个。

    Returns:
        `tuple | None`:
            标准化后的三元组 (subject, predicate, object)，
            格式无效时返回 None。
    """
    try:
        if len(triple) > 3:
            triple = triple[:3]
        elif len(triple) < 3:
            return None
        return tuple(triple)
    except Exception:
        return None


def _count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """计算文本的 token 数。

    Args:
        text (`str`):
            要计数的文本。
        encoding_name (`str`, optional):
            tiktoken 编码名称（默认 "cl100k_base"）。

    Returns:
        `int`:
            token 数量，编码失败时返回 0。
    """
    try:
        return len(tiktoken.get_encoding(encoding_name).encode(text))
    except Exception:
        return 0


class KTBuilder:
    """知识图谱构建器。

    将原始文档经过「分块 → LLM 提取 → 图构建 → 社区检测」流程，
    转换为可用于检索的 KnowledgeGraph 数据和 chunks 数据。

    Attributes:
        config: 全局配置对象。
        dataset_name (`str`):
            数据集标识名，用于选择 prompt 模板和分块策略。
        schema (`dict`):
            加载后的 Schema 配置，定义实体/关系/属性类型。
        graph (`nx.MultiDiGraph`):
            构建中的 NetworkX 多向图。
        node_counter (`int`):
            节点 ID 自增计数器。
        token_len (`int`):
            累计 token 消耗数。
        lock (`threading.RLock`):
            线程安全锁（用于并行文档处理）。
        llm_client (`LLMCompletionCall`):
            同步 LLM 调用客户端。
        all_chunks (`Dict[str, dict]`):
            所有 chunk 的映射表。
            格式: {chunk_id: {"chunk": str, "entities": [entity_name, ...]}}
        mode (`str`):
            构建模式: "novel" / "novel_eng" / "general" 或 "agent"。
        schema_updated (`bool`):
            agent 模式下是否发现了新的 Schema 类型。
    """

    def __init__(
        self,
        dataset_name,
        schema_path=None,
        mode=None,
        config=None,
        schema_data=None,
    ):
        if config is None:
            config = get_config()

        self.config = config
        self.dataset_name = dataset_name
        ds_cfg = config.get_dataset_config(dataset_name)
        self.schema = load_schema(
            schema_path or (ds_cfg.schema_path if ds_cfg else None),
            schema_data,
        )
        self.graph = nx.MultiDiGraph()
        self.node_counter = 0
        self.datasets_no_chunk = config.construction.datasets_no_chunk or []
        self.token_len = 0
        self.lock = threading.RLock()
        self.llm_client = call_llm_api.LLMCompletionCall()
        self.all_chunks: Dict[str, dict] = {}
        self.mode = mode or config.construction.mode
        self.schema_updated = False

        self._encoding_name = getattr(
            config.construction, "encoding_name", "cl100k_base"
        )

    def chunk_text(self, text) -> Tuple[List[str], Dict[str, str]]:
        """将文档文本分块。

        根据数据集是否在 datasets_no_chunk 中决定跳过/执行分块。
        使用 langchain RecursiveCharacterTextSplitter 进行递归字符分割。

        Args:
            text (`dict | str`):
                输入文档。dict 格式: {"title": "...", "text": "..."}；
                str 格式为纯文本。

        Returns:
            `Tuple[List[str], Dict[str, str]]`:
                - chunks: 分块后的文本列表，每个元素为一个 chunk 的字符串。
                - chunk2id: chunk_id → chunk 元信息的映射。
                  格式: {chunk_id: {"chunk": str, "entities": []}}
        """
        chunk2id = {}

        if self.dataset_name in self.datasets_no_chunk:
            raw = (
                f"{text.get('title', '')} {text.get('text', '')}".strip()
                if isinstance(text, dict)
                else str(text)
            )
            chunks = [raw]
        else:
            raw_text = (
                f"{text.get('title', '')} {text.get('text', '')}".strip()
                if isinstance(text, dict)
                else str(text)
            )

            chunk_size = getattr(self.config.construction, "chunk_size", 1000)
            overlap = getattr(self.config.construction, "overlap", 200)

            chunks, _ = chunk_text(
                raw_text,
                chunk_size=chunk_size,
                chunk_overlap=overlap,
                encoding_name=self._encoding_name,
            )

        for chunk in chunks:
            try:
                chunk_id = nanoid.generate(size=8)
                chunk2id[chunk_id] = {"chunk": chunk, "entities": []}
            except Exception as e:
                logger.warning(
                    f"Failed to generate chunk id with nanoid: {type(e).__name__}: {e}"
                )

        with self.lock:
            self.all_chunks.update(chunk2id)

        return chunks, chunk2id

    def _parse_json(self, text: str) -> dict | None:
        """解析 LLM 返回的 JSON 文本。

        优先使用 json_repair（容错解析），失败时回退到标准 json.loads。

        Args:
            text (`str`):
                LLM 返回的原始文本。

        Returns:
            `dict | None`:
                解析成功的字典，解析失败返回 None。
        """
        if HAS_JSON_REPAIR:
            try:
                return json_repair.loads(text)
            except Exception:
                pass
        try:
            return json.loads(text)
        except (json.JSONDecodeError, Exception):
            return None

    def extract_with_llm(self, prompt: str):
        """调用 LLM 提取结构化的实体/关系/属性数据。

        解析 LLM 的 JSON 响应，失败时返回空结构的 JSON 字符串。

        Args:
            prompt (`str`):
                完整的 LLM prompt（包含 chunk 文本和 schema 信息）。

        Returns:
            `str`:
                JSON 字符串。成功时包含 LLM 提取的 attributes/triples/entity_types；
                失败时返回 '{"attributes": {}, "triples": [], "entity_types": {}}'。
        """
        response = self.llm_client.call_api(prompt)
        parsed_dict = self._parse_json(response)
        if parsed_dict is None:
            logger.warning(f"LLM 返回内容解析失败，使用空结果回退: {response[:200]}")
            return json.dumps({"attributes": {}, "triples": [], "entity_types": {}})
        return json.dumps(parsed_dict, ensure_ascii=False)

    def _get_construction_prompt(self, chunk: str) -> str:
        """根据数据集类型和模式获取构建提示词。

        支持 novel / novel_eng / general 三种基础类型，
        agent 模式会附加 schema 演化指令。

        Args:
            chunk (`str`):
                待处理的文本块。

        Returns:
            `str`:
                格式化后的 LLM prompt 字符串，包含 schema 定义和 chunk 文本。
        """
        recommend_schema = json.dumps(self.schema, ensure_ascii=False)
        prompt_type_map = {"novel": "novel", "novel_eng": "novel_eng"}
        base_prompt_type = prompt_type_map.get(self.dataset_name, "general")

        if self.mode == "agent":
            prompt_type = f"{base_prompt_type}_agent"
        else:
            prompt_type = base_prompt_type

        return self.config.get_prompt_formatted(
            "construction", prompt_type, schema=recommend_schema, chunk=chunk
        )

    def _validate_and_parse_llm_response(
        self, prompt: str, llm_response: str
    ) -> dict | None:
        """验证并解析 LLM 返回的 JSON 响应。

        同时累计 token 消耗量用于成本统计。

        Args:
            prompt (`str`):
                发送给 LLM 的 prompt（用于 token 计数）。
            llm_response (`str`):
                LLM 返回的原始文本。

        Returns:
            `dict | None`:
                解析后的字典。包含 attributes, triples, entity_types 等字段。
                llm_response 为 None 时返回 None。
        """
        if llm_response is None:
            return None
        self.token_len += _count_tokens(prompt + llm_response, self._encoding_name)
        return self._parse_json(llm_response)

    def _find_or_create_entity(
        self,
        entity_name: str,
        chunk_id: int,
        entity_type: str = None,
        file_name: str = "",
        description: str = "",
    ) -> str:
        """查找或创建实体节点（按名称去重）。

        如果已存在同名实体节点，直接返回现有节点 ID；
        否则创建新的实体节点（label="entity", level=2）。

        Args:
            entity_name (`str`):
                实体名称。
            chunk_id (`int`):
                关联的 chunk ID，存入节点属性用于溯源。
            entity_type (`str`, optional):
                Schema 类型（如 "person", "drug"），存入节点 schema_type 属性。
            file_name (`str`, optional):
                来源文件名，用于多文件溯源。
            description (`str`, optional):
                实体描述文本，由 attributes 列表拼接而成。

        Returns:
            `str`:
                实体节点 ID（如 "entity_0", "entity_1"）。
        """
        with self.lock:
            entity_node_id = next(
                (
                    n
                    for n, d in self.graph.nodes(data=True)
                    if d.get("label") == "entity"
                    and d["properties"]["name"] == entity_name
                ),
                None,
            )
            if not entity_node_id:
                entity_node_id = f"entity_{self.node_counter}"
                properties = {"name": entity_name, "chunk id": chunk_id}
                if entity_type:
                    properties["schema_type"] = entity_type
                if description:
                    properties["description"] = description
                if file_name:
                    properties["file_name"] = file_name
                self.graph.add_node(
                    entity_node_id, label="entity", properties=properties, level=2
                )
                self.node_counter += 1
            return entity_node_id

    def _process_attributes(
        self,
        extracted_attr: dict,
        chunk_id: int,
        entity_types: dict = {},
        file_name: str = "",
    ) -> dict:
        """处理 LLM 提取的属性数据。

        为每个实体做两件事：
        1. 将属性列表拼接为描述文本（description），存入实体节点
        2. 为每个属性值创建属性节点（label="attribute", level=1），
           通过 has_attribute 边连接到实体节点（用于检索路径）

        Args:
            extracted_attr (`dict`):
                LLM 提取的属性映射。
                格式: {"实体名": ["属性值1", "属性值2"]}
            chunk_id (`int`):
                当前处理的 chunk ID。
            entity_types (`dict`, optional):
                实体类型映射。格式: {"实体名": "schema_type"}
            file_name (`str`, optional):
                来源文件名。

        Returns:
            `dict`:
                实体描述映射。格式: {"实体名": "属性值1，属性值2"}
                供 _process_triples 使用，确保同一文档中实体描述一致。
        """
        entity_descriptions = {}
        for entity, attributes in extracted_attr.items():
            desc = (
                "，".join(str(a) for a in attributes)
                if isinstance(attributes, list)
                else str(attributes)
            )
            entity_descriptions[entity] = desc

            for attr in attributes:
                attr_node_id = f"attr_{self.node_counter}"
                attr_props = {"name": attr, "chunk id": chunk_id}
                if file_name:
                    attr_props["file_name"] = file_name
                self.graph.add_node(
                    attr_node_id,
                    label="attribute",
                    properties=attr_props,
                    level=1,
                )
                self.node_counter += 1
                entity_type = entity_types.get(entity) if entity_types else None
                entity_node_id = self._find_or_create_entity(
                    entity, chunk_id, entity_type, file_name, description=desc
                )
                self.graph.add_edge(
                    entity_node_id, attr_node_id, relation="has_attribute"
                )
        return entity_descriptions

    def _process_triples(
        self,
        extracted_triples: list,
        chunk_id: int,
        entity_types: dict = {},
        file_name: str = "",
        entity_descriptions: dict = None,
    ):
        """处理 LLM 提取的三元组（关系）数据。

        每个三元组 [subject, predicate, object] 转换为图的一条边：
        - 头实体节点 → 关系 → 尾实体节点
        如果实体尚未创建（未在 attributes 中出现），也会自动创建实体节点。

        Args:
            extracted_triples (`list`):
                LLM 提取的三元组列表。
                每个元素格式: ["头实体", "关系", "尾实体"]
            chunk_id (`int`):
                当前处理的 chunk ID。
            entity_types (`dict`, optional):
                实体类型映射。格式: {"实体名": "schema_type"}
            file_name (`str`, optional):
                来源文件名。
            entity_descriptions (`dict | None`, optional):
                实体描述映射（来自 _process_attributes 的返回值）。
                格式: {"实体名": "描述文本"}
        """
        if entity_descriptions is None:
            entity_descriptions = {}
        for triple in extracted_triples:
            validated_triple = _validate_triple_format(triple)
            if not validated_triple:
                continue
            subj, pred, obj = validated_triple
            subj_type = entity_types.get(subj) if entity_types else None
            obj_type = entity_types.get(obj) if entity_types else None
            subj_desc = entity_descriptions.get(subj, "")
            obj_desc = entity_descriptions.get(obj, "")
            subj_node_id = self._find_or_create_entity(
                subj, chunk_id, subj_type, file_name, description=subj_desc
            )
            obj_node_id = self._find_or_create_entity(
                obj, chunk_id, obj_type, file_name, description=obj_desc
            )
            self.graph.add_edge(subj_node_id, obj_node_id, relation=pred)

    def process_level1_level2(self, chunk: str, chunk_id: int, file_name: str = ""):
        """处理一个 chunk：LLM 提取 → 属性处理 → 三元组处理。

        调用 LLM 提取结构化数据 → 分别处理 attributes 和 triples →
        更新 all_chunks 的 entities 列表。

        Args:
            chunk (`str`):
                文本块内容。
            chunk_id (`int`):
                chunk 的唯一标识。
            file_name (`str`, optional):
                源文件名（用于溯源）。

        LLM 响应格式:
            ```json
            {
                "attributes": {"实体名": ["属性值1"]},
                "triples": [["头实体", "关系", "尾实体"]],
                "entity_types": {"实体名": "schema_type"}
            }
            ```
        """
        prompt = self._get_construction_prompt(chunk)
        llm_response = self.extract_with_llm(prompt)
        parsed_response = self._validate_and_parse_llm_response(prompt, llm_response)
        if not parsed_response:
            return

        extracted_attr = parsed_response.get("attributes", {})
        extracted_triples = parsed_response.get("triples", [])
        entity_types = parsed_response.get("entity_types", {})
        entity_names = list(entity_types.keys())

        with self.lock:
            if self.mode == "agent":
                new_schema_types = parsed_response.get("new_schema_types", {})
                if new_schema_types:
                    self._update_schema_with_new_types(new_schema_types)
            if chunk_id in self.all_chunks:
                self.all_chunks[chunk_id]["entities"] = entity_names
            entity_descriptions = self._process_attributes(
                extracted_attr, chunk_id, entity_types, file_name
            )
            self._process_triples(
                extracted_triples,
                chunk_id,
                entity_types,
                file_name,
                entity_descriptions,
            )

    def _update_schema_with_new_types(self, new_schema_types: Dict[str, List[str]]):
        """合并 agent 模式下 LLM 发现的新 Schema 类型。

        当 LLM 在 agent 模式下发现了当前 Schema 中不存在的实体/关系/属性类型时，
        将其合并到 self.schema 中，并标记 schema_updated=True 以便后续持久化。

        Args:
            new_schema_types (`Dict[str, List[str]]`):
                新发现的 Schema 类型。格式: {"entity_types": [...], "relation_types": [...]}
        """
        try:
            updated = merge_schema_types(self.schema, new_schema_types)
            if updated:
                self.schema_updated = True
                logger.info(f"Schema updated with new types: {new_schema_types}")
        except Exception as e:
            logger.error(
                f"Failed to update schema with new types: {type(e).__name__}: {e}"
            )

    def process_level4(self):
        """社区检测（Level 4）。

        对图中的所有实体节点（level=2）执行社区检测：
        1. FastTreeComm: KMeans 聚类 → 层次化合并
        2. LLM 命名：为每个社区生成名称、描述、关键词
        3. 社区节点存入图（label="community", level=4）

        社区检测结果存储在图中，通过 member_of 边关联实体与社区。
        """
        level2_nodes = [n for n, d in self.graph.nodes(data=True) if d["level"] == 2]
        start_comm = time.time()
        _tree_comm = tree_comm.FastTreeComm(
            self.graph,
            struct_weight=self.config.tree_comm.struct_weight,
            config=self.config,
            chunks_data=self.all_chunks,
        )
        comm_to_nodes = _tree_comm.detect_communities(level2_nodes)
        _tree_comm.create_super_nodes_with_keywords(comm_to_nodes, level=4)
        end_comm = time.time()
        logger.info(f"Community Indexing Time: {end_comm - start_comm}s")

    def process_document(self, doc: Dict[str, Any]):
        """处理单个文档：分块 → 逐块提取 → 构建图。

        每个 chunk 调用 process_level1_level2() 进行 LLM 提取和图构建。
        当没有标题时使用空字符串作为 file_name。

        Args:
            doc (`Dict[str, Any]`):
                文档字典。格式: {"title": str, "text": str}
                如果 doc 不是 dict 类型，会被当作纯文本处理（title 为空）。

        Raises:
            ValueError: 文档为空或文档内容无法生成有效 chunk 时抛出。
        """
        try:
            if not doc:
                raise ValueError("Document is empty or None")
            file_name = doc.get("title", "") if isinstance(doc, dict) else ""
            chunks, chunk2id = self.chunk_text(doc)
            if not chunks or not chunk2id:
                raise ValueError(
                    f"No valid chunks generated from document. Chunks: {len(chunks)}, Chunk2ID: {len(chunk2id)}"
                )
            for chunk in chunks:
                id = next(
                    (
                        key
                        for key, value in chunk2id.items()
                        if isinstance(value, dict) and value.get("chunk") == chunk
                    ),
                    None,
                )
                if id is None:
                    id = nanoid.generate(size=8)
                    chunk2id[id] = {"chunk": chunk, "entities": []}
                    with self.lock:
                        self.all_chunks[id] = chunk2id[id]
                self.process_level1_level2(chunk, id, file_name)
        except Exception as e:
            error_msg = f"Error processing document: {type(e).__name__}: {str(e)}"
            raise Exception(error_msg) from e

    def process_all_documents(self, documents: List[Dict[str, Any]]) -> None:
        """并发处理所有文档。

        使用 ThreadPoolExecutor 并行处理多个文档（由 config.construction.max_workers 控制）。
        全部文档处理完成后，执行去重和社区检测。

        Args:
            documents (`List[Dict[str, Any]]`):
                文档列表。每个元素格式: {"title": str, "text": str}

        Raises:
            Exception: ThreadPoolExecutor 发生错误时抛出。
        """
        max_workers = min(
            self.config.construction.max_workers, (os.cpu_count() or 1) + 4
        )
        start_construct = time.time()
        total_docs = len(documents)

        logger.info(
            f"Starting processing {total_docs} documents with {max_workers} workers..."
        )

        all_futures = []
        processed_count = 0
        failed_count = 0

        try:
            with futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                all_futures = [
                    executor.submit(self.process_document, doc) for doc in documents
                ]

                for i, future in enumerate(futures.as_completed(all_futures)):
                    try:
                        future.result()
                        processed_count += 1
                        if processed_count % 5 == 0 or processed_count == total_docs:
                            elapsed_time = time.time() - start_construct
                            avg_time_per_doc = (
                                elapsed_time / processed_count
                                if processed_count > 0
                                else 0
                            )
                            remaining_docs = total_docs - processed_count
                            estimated_remaining_time = remaining_docs * avg_time_per_doc
                            logger.info(
                                f"Progress: {processed_count}/{total_docs} documents processed "
                                f"({processed_count / total_docs * 100:.1f}%) "
                                f"[{failed_count} failed] "
                                f"ETA: {estimated_remaining_time / 60:.1f} minutes"
                            )
                    except Exception:
                        failed_count += 1
        except Exception as e:
            logger.error(
                f"ThreadPoolExecutor 处理文档时发生错误: {type(e).__name__}: {e}"
            )
            raise

        end_construct = time.time()
        logger.info(f"Construction Time: {end_construct - start_construct}s")
        logger.info(f"Successfully processed: {processed_count}/{total_docs} documents")
        logger.info(f"Failed: {failed_count} documents")
        logger.info(f"{'Processing Level 3 and 4':-^40}")
        self.triple_deduplicate()
        self.process_level4()

    def triple_deduplicate(self):
        """去重图中的三元组边。

        由于多个 chunk 可能提取出相同的 (头节点, 关系, 尾节点) 三元组，
        此方法将重复边合并为一条，节点保持不变。
        """
        new_graph = nx.MultiDiGraph()
        for node, node_data in self.graph.nodes(data=True):
            new_graph.add_node(node, **node_data)
        seen_triples = set()
        for u, v, key, data in self.graph.edges(keys=True, data=True):
            relation = data.get("relation")
            if (u, v, relation) not in seen_triples:
                seen_triples.add((u, v, relation))
                new_graph.add_edge(u, v, **data)
        self.graph = new_graph

    def format_output(self) -> List[Dict[str, Any]]:
        """将 NetworkX 图格式化为图谱 JSON 格式。

        遍历图中所有边，输出三节点格式以便序列化存储到 DB。

        Returns:
            `List[Dict[str, Any]]`:
                图谱数据列表，每个元素格式:
                ```
                {
                    "start_node": {
                        "label": "entity|attribute|community",
                        "properties": {name, chunk_id, schema_type?, description?, file_name?, ...}
                    },
                    "relation": "关系名称",
                    "end_node": {
                        "label": "entity|attribute|keyword|community",
                        "properties": {...}
                    }
                }
                ```
        """
        output = []
        for u, v, data in self.graph.edges(data=True):
            u_data = self.graph.nodes[u]
            v_data = self.graph.nodes[v]
            relationship = {
                "start_node": {
                    "label": u_data["label"],
                    "properties": u_data["properties"],
                },
                "relation": data.get("relation", "related_to"),
                "end_node": {
                    "label": v_data["label"],
                    "properties": v_data["properties"],
                },
            }
            output.append(relationship)
        return output

    def _load_json_file(self, path: str):
        """从文件加载 JSON 数据（优先使用 json_repair 容错加载）。

        Args:
            path (`str`):
                JSON 文件路径。

        Returns:
            `dict | list`:
                解析后的 JSON 数据。
        """
        if HAS_JSON_REPAIR:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json_repair.load(f)
            except Exception:
                pass
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def build_knowledge_graph(self, corpus=None, documents=None):
        """完整知识图谱构建入口。

        处理流程：
        1. 从 documents 或 corpus 文件加载文档
        2. process_all_documents() 并发处理
        3. format_output() 输出为可序列化的图谱数据

        Args:
            corpus (`str`, optional):
                包含文档列表的 JSON 文件路径（documents 为 None 时使用）。
            documents (`List[Dict] | None`, optional):
                文档列表。每个元素格式: {"title": str, "text": str}

        Returns:
            `List[Dict]`:
                图谱边列表，每边格式为 {start_node: {label, properties}, relation, end_node: {label, properties}}。
                此返回值可直接存入 KnowledgeGraph.graph_data 字段。
        """
        logger.info(f"{'Start Building':=^40}")
        if documents is None:
            documents = self._load_json_file(corpus)
        self.process_all_documents(documents)
        logger.info(f"All Process finished, token cost: {self.token_len}")
        output = self.format_output()
        return output
