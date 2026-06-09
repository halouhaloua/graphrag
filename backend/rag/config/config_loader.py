"""
Configuration loader and manager for KT-RAG framework.
Handles loading, validation, and access to configuration parameters.

Config classes:
  - RetrievalTypeScale: per-type (micro/macro) top-k scaling factors
  - RetrievalConfig: main retrieval config, includes retrieval_type_scales
"""

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import torch

from rag.config.prompts import prompts
from loguru import logger


_embedding_model_instance = None


def _get_embedding_model():
    global _embedding_model_instance
    if _embedding_model_instance is not None:
        return _embedding_model_instance
    from sentence_transformers import SentenceTransformer

    default_path = str(Path(__file__).parent.parent.parent.parent / "bge-small-zh-v1.5")
    model_path = os.environ.get("RAG_EMBEDDING_MODEL_PATH", default_path)
    _embedding_model_instance = SentenceTransformer(model_path)
    if torch.cuda.is_available():
        _embedding_model_instance = _embedding_model_instance.to("cuda")
        logger.info("Embedding model moved to GPU")
    else:
        logger.info("Embedding model running on CPU")
    return _embedding_model_instance


# Eager load at module import
# _get_embedding_model()


file_path = Path(__file__).parent.parent


@dataclass
class DatasetConfig:
    corpus_path: str
    qa_path: str
    schema_path: str
    graph_output: str


@dataclass
class TriggersConfig:
    constructor_trigger: bool = True
    retrieve_trigger: bool = True
    mode: str = "agent"


@dataclass
class ConstructionConfig:
    mode: str = "agent"
    max_workers: int = 5
    datasets_no_chunk: list = field(default_factory=list)
    chunk_size: int = 512
    overlap: int = 100
    encoding_name: str = "cl100k_base"


@dataclass
class TreeCommConfig:
    struct_weight: float = 0.3
    enable_fast_mode: bool = True

    def get_embedding_model(self):
        return _get_embedding_model()


@dataclass
class FAISSConfig:
    search_k: int = 50
    max_workers: int = 4
    device: str = os.environ.get("RAG_FAISS_DEVICE", "cpu")


@dataclass
class AgentConfig:
    max_steps: int = 5
    enable_ircot: bool = False
    enable_parallel_subquestions: bool = True


@dataclass
class RetrievalTypeScale:
    """检索类型对应的 top_k 缩放配置"""
    path1_scale: float = 1.0
    path2_scale: float = 1.0
    chunk_scale: float = 1.0


@dataclass
class RetrievalConfig:
    top_k_triple: int = 5
    top_k_chunk: int = 5
    recall_paths: int = 2
    top_k_filter: int = 20
    similarity_threshold: float = 0.3
    enable_query_enhancement: bool = True
    enable_reranking: bool = True
    enable_high_recall: bool = True
    enable_caching: bool = True
    triple_weight: float = 0.3
    retrieval_type_scales: Dict[str, "RetrievalTypeScale"] = field(default_factory=lambda: {
        "micro": RetrievalTypeScale(path1_scale=1.5, path2_scale=0.5, chunk_scale=1.5),
        "macro": RetrievalTypeScale(path1_scale=0.5, path2_scale=1.5, chunk_scale=0.5),
    })
    cache_dir: str = str(file_path / "retriever/faiss_cache_new")
    faiss: FAISSConfig = None
    agent: AgentConfig = None

    def __post_init__(self):
        if self.faiss is None:
            self.faiss = FAISSConfig()
        if self.agent is None:
            self.agent = AgentConfig()


@dataclass
class EmbeddingsConfig:
    def get_model(self):
        return _get_embedding_model()

    batch_size: int = 32
    max_length: int = 512


@dataclass
class OutputConfig:
    base_dir: str = str(file_path / "output")
    graphs_dir: str = str(file_path / "output/graphs")
    chunks_dir: str = str(file_path / "output/chunks")
    logs_dir: str = str(file_path / "output/logs")
    save_intermediate_results: bool = True
    save_chunk_details: bool = True


@dataclass
class PerformanceConfig:
    parallel_processing: bool = True
    max_workers: int = 32
    batch_size: int = 16
    memory_optimization: bool = True


class ConfigManager:
    def __init__(self):
        self.datasets: Dict[str, DatasetConfig] = {
            "demo": DatasetConfig(
                corpus_path="",
                qa_path="",
                schema_path=str(file_path / "schemas/demo.json"),
                graph_output=str(file_path / "output/graphs/demo_new.json"),
            )
        }
        self.prompts: Dict[str, Any] = prompts
        self.triggers = TriggersConfig()
        self.construction = ConstructionConfig()
        self.tree_comm = TreeCommConfig()
        self.retrieval = RetrievalConfig()
        self.embeddings = EmbeddingsConfig()
        self.output = OutputConfig()
        self.performance = PerformanceConfig()
        self.retrieval.faiss = FAISSConfig()
        self.retrieval.agent = AgentConfig()
        self._validate_config()
        logger.info("Configuration loaded from CODE (no YAML) ")

    def _validate_config(self):
        valid_modes = ["agent", "noagent"]
        if self.triggers.mode not in valid_modes:
            raise ValueError(f"mode must be {valid_modes}")

    def get_dataset_config(self, dataset_name: str) -> Optional[DatasetConfig]:
        return self.datasets.get(dataset_name)

    def get_prompt(self, category: str, prompt_type: str) -> str:
        prompt = self.prompts.get(f"{category}_{prompt_type}")
        return prompt

    def get_prompt_formatted(self, category: str, prompt_type: str, **kwargs) -> str:
        return self.get_prompt(category, prompt_type).format(**kwargs)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "datasets": {name: asdict(cfg) for name, cfg in self.datasets.items()},
            "triggers": asdict(self.triggers),
            "construction": asdict(self.construction),
            "tree_comm": asdict(self.tree_comm),
            "retrieval": asdict(self.retrieval),
            "embeddings": asdict(self.embeddings),
            "prompts": self.prompts,
            "output": asdict(self.output),
            "performance": asdict(self.performance),
        }

    def create_output_directories(self):
        for d in [
            self.output.base_dir,
            self.output.graphs_dir,
            self.output.chunks_dir,
            self.output.logs_dir,
        ]:
            os.makedirs(d, exist_ok=True)

    def set_ircot_enabled(self, enabled: bool):
        self.retrieval.agent.enable_ircot = enabled
        logger.info(f"IRCoT {'enabled' if enabled else 'disabled'}")

    def get_ircot_enabled(self) -> bool:
        return self.retrieval.agent.enable_ircot

    def to_dict_ircot(self) -> dict:
        return {
            "enable_ircot": self.retrieval.agent.enable_ircot,
            "max_steps": self.retrieval.agent.max_steps,
        }


_config_instance: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigManager()
    return _config_instance


def reload_config() -> ConfigManager:
    global _config_instance
    _config_instance = ConfigManager()
    return _config_instance
