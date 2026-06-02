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
    """Validate and normalize triple format, returning (subject, predicate, object) or None."""
    try:
        if len(triple) > 3:
            triple = triple[:3]
        elif len(triple) < 3:
            return None
        return tuple(triple)
    except Exception:
        return None


def _count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    try:
        return len(tiktoken.get_encoding(encoding_name).encode(text))
    except Exception:
        return 0


class KTBuilder:
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
                chunk2id[chunk_id] = {"chunk": chunk, "macro_tags": {}, "entities": []}
            except Exception as e:
                logger.warning(
                    f"Failed to generate chunk id with nanoid: {type(e).__name__}: {e}"
                )

        with self.lock:
            self.all_chunks.update(chunk2id)

        return chunks, chunk2id

    def _parse_json(self, text: str) -> dict | None:
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
        response = self.llm_client.call_api(prompt)
        parsed_dict = self._parse_json(response)
        if parsed_dict is None:
            logger.warning(f"LLM 返回内容解析失败，使用空结果回退: {response[:200]}")
            return json.dumps({"attributes": {}, "triples": [], "entity_types": {}})
        return json.dumps(parsed_dict, ensure_ascii=False)

    def _get_construction_prompt(self, chunk: str) -> str:
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
    ) -> str:
        with self.lock:
            entity_node_id = next(
                (
                    n
                    for n, d in self.graph.nodes(data=True)
                    if d.get("label") == "entity" and d["properties"]["name"] == entity_name
                ),
                None,
            )
            if not entity_node_id:
                entity_node_id = f"entity_{self.node_counter}"
                properties = {"name": entity_name, "chunk id": chunk_id}
                if entity_type:
                    properties["schema_type"] = entity_type
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
    ):
        for entity, attributes in extracted_attr.items():
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
                    entity, chunk_id, entity_type, file_name
                )
                self.graph.add_edge(
                    entity_node_id, attr_node_id, relation="has_attribute"
                )

    def _process_triples(
        self,
        extracted_triples: list,
        chunk_id: int,
        entity_types: dict = {},
        file_name: str = "",
    ):
        for triple in extracted_triples:
            validated_triple = _validate_triple_format(triple)
            if not validated_triple:
                continue
            subj, pred, obj = validated_triple
            subj_type = entity_types.get(subj) if entity_types else None
            obj_type = entity_types.get(obj) if entity_types else None
            subj_node_id = self._find_or_create_entity(
                subj, chunk_id, subj_type, file_name
            )
            obj_node_id = self._find_or_create_entity(
                obj, chunk_id, obj_type, file_name
            )
            self.graph.add_edge(subj_node_id, obj_node_id, relation=pred)

    def process_level1_level2(self, chunk: str, chunk_id: int, file_name: str = ""):
        prompt = self._get_construction_prompt(chunk)
        llm_response = self.extract_with_llm(prompt)
        parsed_response = self._validate_and_parse_llm_response(prompt, llm_response)
        if not parsed_response:
            return

        extracted_attr = parsed_response.get("attributes", {})
        extracted_triples = parsed_response.get("triples", [])
        entity_types = parsed_response.get("entity_types", {})
        macro_tags = parsed_response.get("macro_tags", {})
        entity_names = list(entity_types.keys())

        with self.lock:
            if self.mode == "agent":
                new_schema_types = parsed_response.get("new_schema_types", {})
                if new_schema_types:
                    self._update_schema_with_new_types(new_schema_types)
            if chunk_id in self.all_chunks:
                self.all_chunks[chunk_id]["macro_tags"] = macro_tags
                self.all_chunks[chunk_id]["entities"] = entity_names
            self._process_attributes(extracted_attr, chunk_id, entity_types, file_name)
            self._process_triples(extracted_triples, chunk_id, entity_types, file_name)

    def _update_schema_with_new_types(self, new_schema_types: Dict[str, List[str]]):
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
                    chunk2id[id] = {"chunk": chunk, "macro_tags": {}, "entities": []}
                    with self.lock:
                        self.all_chunks[id] = chunk2id[id]
                self.process_level1_level2(chunk, id, file_name)
        except Exception as e:
            error_msg = f"Error processing document: {type(e).__name__}: {str(e)}"
            raise Exception(error_msg) from e

    def process_all_documents(self, documents: List[Dict[str, Any]]) -> None:
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
            logger.error(f"ThreadPoolExecutor 处理文档时发生错误: {type(e).__name__}: {e}")
            raise

        end_construct = time.time()
        logger.info(f"Construction Time: {end_construct - start_construct}s")
        logger.info(f"Successfully processed: {processed_count}/{total_docs} documents")
        logger.info(f"Failed: {failed_count} documents")
        logger.info(f"{'Processing Level 3 and 4':-^40}")
        self.triple_deduplicate()
        self.process_level4()

    def triple_deduplicate(self):
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
        if HAS_JSON_REPAIR:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json_repair.load(f)
            except Exception:
                pass
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def build_knowledge_graph(self, corpus=None, documents=None):
        logger.info(f"{'Start Building':=^40}")
        if documents is None:
            documents = self._load_json_file(corpus)
        self.process_all_documents(documents)
        logger.info(f"All Process finished, token cost: {self.token_len}")
        output = self.format_output()
        return output
