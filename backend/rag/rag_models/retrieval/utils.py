"""检索模块通用工具函数

功能：
- 设备解析（CUDA/CPU）
- 嵌入缓存保存/加载（支持 .pt 和 .npz 格式）
- pickle 缓存保存/加载（带可选 consistency 校验）
- 余弦相似度批量计算
- FAISS 中文路径安全映射（MD5 哈希）
- LRU 缓存淘汰
- 节点文本提取工具（extract_node_name_and_description / is_valid_node_text）

数据流（嵌入缓存）：
  save_embedding_cache({key: tensor}, path)
    → 先尝试 torch.save 保存为 .pt
    → 失败则 fallback 为 np.savez_compressed 保存为 .npz
  load_embedding_cache(path, device)
    → 先尝试 .npz 加载 → 再尝试 .pt 加载
    → 返回 {key: tensor} 或 None

数据流（pickle 缓存）：
  save_pickle_cache(dict, cache_dir, dataset, name)
    → 写入 pickle 文件
  load_pickle_cache(cache_dir, dataset, name, expected_keys)
    → 读取 pickle 文件
    → 可选校验 expected_keys 一致性

FAISS 中文路径处理：
  safe_faiss_path(original_path, cache_root)
    → 检测路径是否含非 ASCII 字符
    → 如果是，用 MD5 哈希生成安全文件名
    → 记录映射到 faiss_path_mapping.json

字符串工具：
  sanitize_string_field(value) → str
  extract_node_name_and_description(node_data) → (name, desc)
  is_valid_node_text(text) → bool
"""

import hashlib
import json
import os
import pickle
from typing import Any, Dict, List, Optional, Set, Union

import numpy as np
import torch
import torch.nn.functional as F


# ─── 设备 ───


def resolve_device(device: Optional[str] = None) -> torch.device:
    """统一的设备解析

    Args:
        device (`str`, optional):
            目标设备名（"cuda" / "cpu"），默认自动检测

    Returns:
        `torch.device`: 解析后的设备对象
    """
    if device is not None:
        if device == "cuda" and not torch.cuda.is_available():
            import logging

            logging.getLogger(__name__).warning(
                "Warning: CUDA requested but not available, falling back to CPU"
            )
            return torch.device("cpu")
        return torch.device(device)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def resolve_device_str(device: Optional[str] = None) -> str:
    """统一的设备解析（返回字符串）

    Args:
        device (`str`, optional): 目标设备名

    Returns:
        `str`: "cuda" 或 "cpu" 字符串
    """
    if device is not None:
        if device == "cuda":
            return "cuda" if torch.cuda.is_available() else "cpu"
        return device
    return "cuda" if torch.cuda.is_available() else "cpu"


# ─── 字符串工具 ───


def sanitize_string_field(value: Any) -> str:
    """将字段值规范化为干净的字符串

    Args:
        value: 任意值（str / list 等）

    Returns:
        `str`: 规范化后的字符串，None 或空时返回空字符串
    """
    if not value:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value).strip()


def extract_node_name_and_description(
    node_data: dict,
) -> tuple[str, str]:
    """从节点数据中提取 name 和 description，统一处理新旧数据结构。

    新格式：{"properties": {"name": "...", "description": "..."}}
    旧格式：{"name": "...", "description": "..."}

    Args:
        node_data (`dict`): 图节点的 data 字典

    Returns:
        `tuple[str, str]`: (name, description)，缺失时为空字符串
    """
    if "properties" in node_data and isinstance(node_data["properties"], dict):
        name = sanitize_string_field(node_data["properties"].get("name", ""))
        description = sanitize_string_field(
            node_data["properties"].get("description", "")
        )
    else:
        name = sanitize_string_field(node_data.get("name", ""))
        description = sanitize_string_field(node_data.get("description", ""))
    return name, description


def is_valid_node_text(text: str) -> bool:
    """检查节点文本是否可用于嵌入计算

    排除空文本和错误标记文本。

    Args:
        text (`str`): 待检查文本

    Returns:
        `bool`: True 表示可用于编码
    """
    return bool(
        text and not text.startswith("[Error") and not text.startswith("[Unknown")
    )


# ─── Torch 安全加载 ───


def torch_safe_load(
    filepath: str, map_location: str = "cpu", weights_only: bool = False
) -> Optional[Dict]:
    """安全的 torch.load（兼容 PyTorch 2.6+）

    处理 numpy._reconstruct 兼容性问题。

    Args:
        filepath (`str`): 文件路径
        map_location (`str`): 映射设备（默认 cpu）
        weights_only (`bool`): 是否仅加载权重（默认 False）

    Returns:
        `Optional[Dict]`: 加载的字典数据，失败返回 None
    """
    try:
        return torch.load(
            filepath, map_location=map_location, weights_only=weights_only
        )
    except TypeError:
        return torch.load(filepath, map_location=map_location)
    except Exception as e:
        if "numpy.core.multiarray._reconstruct" in str(e):
            try:
                import importlib

                torch_serialization = importlib.import_module("torch.serialization")
                torch_serialization.add_safe_globals(
                    ["numpy.core.multiarray._reconstruct"]
                )
                return torch.load(filepath, map_location=map_location)
            except Exception:
                raise e
        raise e


# ─── 嵌入缓存 I/O ───


def save_embedding_cache(
    cache: Dict[Any, Any],
    filepath: str,
    logger=None,
) -> bool:
    """统一的嵌入缓存保存（优先 .pt，fallback .npz）

    输入 cache 为 {key: tensor/ndarray}，
    内部统一转为 numpy 后再决定存储格式。

    Args:
        cache (`Dict[Any, Any]`): {key: tensor/ndarray}
        filepath (`str`): 目标文件路径（.pt 或 .npz）
        logger: 可选的 logger 实例

    Returns:
        `bool`: 保存成功返回 True
    """
    try:
        if not cache:
            return False

        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)

        numpy_cache: Dict[Any, np.ndarray] = {}
        for key, embed in cache.items():
            if embed is None:
                continue
            try:
                if hasattr(embed, "detach"):
                    numpy_cache[key] = embed.detach().cpu().numpy()
                elif isinstance(embed, np.ndarray):
                    numpy_cache[key] = embed
                else:
                    numpy_cache[key] = np.array(embed)
            except Exception:
                continue

        if not numpy_cache:
            return False

        try:
            tensor_cache = {}
            for key, arr in numpy_cache.items():
                if isinstance(arr, np.ndarray):
                    tensor_cache[key] = torch.from_numpy(arr).float()
                else:
                    tensor_cache[key] = arr
            torch.save(tensor_cache, filepath)
        except Exception:
            npz_path = filepath.replace(".pt", ".npz")
            np.savez_compressed(npz_path, **numpy_cache)
            filepath = npz_path

        if logger:
            file_size = os.path.getsize(filepath)
            logger.info(
                f"Saved embedding cache with {len(numpy_cache)} entries to {filepath} (size: {file_size} bytes)"
            )
        return True

    except Exception as e:
        if logger:
            logger.error(f"Error saving embedding cache: {e}")
        return False


def load_embedding_cache(
    filepath: str,
    device: Union[str, torch.device],
    logger=None,
) -> Optional[Dict[Any, torch.Tensor]]:
    """统一的嵌入缓存加载（先试 .npz，再试 .pt）

    自动清理损坏的小文件（< 1000 bytes）。

    Args:
        filepath (`str`): 缓存文件路径（.pt）
        device (`Union[str, torch.device]`): 目标设备
        logger: 可选的 logger 实例

    Returns:
        `Optional[Dict[Any, torch.Tensor]]`:
            {key: tensor} 已移至目标设备，加载失败返回 None
    """
    filepath_npz = filepath.replace(".pt", ".npz")

    def _numpy_load(npz_path: str):
        if not os.path.exists(npz_path):
            return None
        try:
            data = np.load(npz_path)
            if len(data.files) == 0:
                data.close()
                return None
            return data
        except Exception as e:
            if logger:
                logger.error(f"Error loading numpy cache: {e}")
            return None

    def _tensor_load(pt_path: str):
        if not os.path.exists(pt_path):
            return None
        try:
            file_size = os.path.getsize(pt_path)
            if file_size < 1000:
                if logger:
                    logger.warning(
                        f"Warning: Cache file too small ({file_size} bytes), likely empty or corrupted"
                    )
                return None
            return torch_safe_load(pt_path, map_location="cpu", weights_only=False)
        except Exception as e:
            if logger:
                logger.error(f"Error loading embedding cache: {e}")
            try:
                os.remove(pt_path)
                if logger:
                    logger.info(f"Removed corrupted cache file: {pt_path}")
            except Exception:
                pass
            return None

    def _items_to_tensors(raw_cache: Dict) -> Dict[Any, torch.Tensor]:
        result: Dict[Any, torch.Tensor] = {}
        for key, embed in raw_cache.items():
            if embed is None:
                continue
            try:
                if isinstance(embed, np.ndarray):
                    emb = torch.from_numpy(embed).float()
                else:
                    emb = embed.cpu() if hasattr(embed, "cpu") else embed
                if isinstance(device, torch.device):
                    target = device
                else:
                    target = torch.device(
                        "cuda"
                        if (device == "cuda" and torch.cuda.is_available())
                        else device
                    )
                if target.type == "cuda" and torch.cuda.is_available():
                    emb = emb.to(target)
                else:
                    emb = emb.to("cpu")
                result[key] = emb
            except Exception as e:
                if logger:
                    logger.warning(f"Warning: Failed to load embedding for {key}: {e}")
                continue
        return result

    numpy_data = _numpy_load(filepath_npz)
    if numpy_data is not None:
        try:
            raw = {}
            for k in numpy_data.files:
                raw[k] = numpy_data[k]
            numpy_data.close()
            result = _items_to_tensors(raw)
            if logger and result:
                logger.info(
                    f"Loaded embedding cache with {len(result)} entries from {filepath_npz}"
                )
            return result if result else None
        except Exception as e:
            if logger:
                logger.error(f"Error loading embedding cache from {filepath_npz}: {e}")
            return None

    raw_cache = _tensor_load(filepath)
    if raw_cache is None:
        return None
    if not raw_cache:
        if logger:
            logger.warning("Warning: Loaded cache is empty")
        return None

    result = _items_to_tensors(raw_cache)
    if logger and result:
        logger.info(
            f"Loaded embedding cache with {len(result)} entries from {filepath}"
        )
    return result if result else None


# ─── 缓存一致性 ───


def check_cache_consistency(
    current_set: Set,
    cached_set: Set,
    name: str = "cache",
    tolerance: float = 0.1,
    logger=None,
) -> bool:
    """检查缓存键集合与当前数据是否一致

    允许一定比例的额外条目（容忍度）。

    Args:
        current_set (`Set`): 当前数据的键集合
        cached_set (`Set`): 缓存的键集合
        name (`str`): 缓存名称（日志用）
        tolerance (`float`): 额外条目容忍比例
        logger: logger 实例

    Returns:
        `bool`: True 表示一致
    """
    try:
        missing = current_set - cached_set
        if missing:
            if logger:
                logger.info(f"{name} missing {len(missing)} entries from current data")
            return False

        extra = cached_set - current_set
        if len(extra) > len(current_set) * tolerance:
            if logger:
                logger.info(
                    f"{name} has too many extra entries: {len(extra)} extra vs {len(current_set)} current"
                )
            return False

        return True

    except Exception as e:
        if logger:
            logger.error(f"Error checking {name} consistency: {e}")
        return False


def check_cache_consistency_simple(
    current_set: Set,
    cache_dict: Dict,
    name: str = "cache",
    logger=None,
) -> bool:
    """检查缓存字典的键与当前数据集是否一致（简化版）

    Args:
        current_set (`Set`): 当前数据的键集合
        cache_dict (`Dict`): 缓存字典（只检查键）
        name (`str`): 缓存名称
        logger: logger 实例

    Returns:
        `bool`: True 表示一致
    """
    return check_cache_consistency(
        current_set, set(cache_dict.keys()), name=name, logger=logger
    )


# ─── LRU 缓存淘汰 ───


def evict_lru_cache(cache: Dict, max_size: int, strategy: str = "oldest") -> None:
    """当缓存超过最大大小时淘汰条目

    Args:
        cache (`Dict`): 待管理的缓存字典（会被原地修改）
        max_size (`int`): 最大条目数
        strategy (`str`):
            淘汰策略：
            - "oldest"（默认）：删除最旧的条目
            - "recent"：保留最近的条目
    """
    if len(cache) <= max_size:
        return
    if strategy == "oldest":
        remove_count = len(cache) - max_size
        oldest = list(cache.keys())[:remove_count]
        for key in oldest:
            del cache[key]
    elif strategy == "recent":
        recent = list(cache.keys())[-max_size:]
        keys_to_remove = [k for k in cache if k not in recent]
        for key in keys_to_remove:
            del cache[key]


# ─── 文件安全删除 ───


def remove_file_safe(filepath: str, logger=None) -> None:
    """安全删除文件，记录错误

    Args:
        filepath (`str`): 要删除的文件路径
        logger: logger 实例
    """
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        if logger:
            logger.warning(f"Failed to remove {filepath}: {e}")


safe_remove = remove_file_safe  # 别名


# ─── 余弦相似度 ───


def batch_compute_similarities(
    query_embed: torch.Tensor,
    embeddings_list: List[torch.Tensor],
    names: List[str],
) -> Dict[str, float]:
    """批量计算 query 与多个 embeddings 的余弦相似度

    Args:
        query_embed (`torch.Tensor`): 查询嵌入向量
        embeddings_list (`List[torch.Tensor]`): 待比较的嵌入向量列表
        names (`List[str]`): 对应名称（作为返回字典的键）

    Returns:
        `Dict[str, float]`:
            {name: cosine_similarity}，相似度被 clamp 到 [0.0, ...]
    """
    if not embeddings_list:
        return {}
    embeddings_tensor = torch.stack(embeddings_list)
    similarities = F.cosine_similarity(
        query_embed.unsqueeze(0), embeddings_tensor, dim=1
    )
    return {names[i]: max(0.0, similarities[i].item()) for i in range(len(names))}


# ─── pickle 缓存 I/O ───


def save_pickle_cache(
    cache: Dict,
    cache_dir: str,
    dataset: str,
    name: str,
    logger=None,
) -> bool:
    """泛型 pickle 缓存保存

    Args:
        cache (`Dict`): 待保存的字典
        cache_dir (`str`): 缓存根目录
        dataset (`str`): 数据集名称
        name (`str`): 缓存名称（用作文件名）
        logger: logger 实例

    Returns:
        `bool`: 保存成功返回 True
    """
    path = f"{cache_dir}/{dataset}/{name}.pkl"
    try:
        if not cache:
            return False
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(cache, f)
        if logger:
            logger.info(f"Saved {name} with {len(cache)} entries to {path}")
        return True
    except Exception as e:
        if logger:
            logger.error(f"Error saving {name}: {e}")
        return False


def load_pickle_cache(
    cache_dir: str,
    dataset: str,
    name: str,
    expected_keys: Set = None,
    logger=None,
) -> Optional[Dict]:
    """泛型 pickle 缓存加载

    自动校验文件大小（< 1000 bytes 视为损坏），
    可选校验 expected_keys 一致性。

    Args:
        cache_dir (`str`): 缓存根目录
        dataset (`str`): 数据集名称
        name (`str`): 缓存名称（文件名）
        expected_keys (`Set`, optional):
            期望的键集合，如果提供且不匹配则返回 None
        logger: logger 实例

    Returns:
        `Optional[Dict]`:
            加载的字典数据，损坏或不一致返回 None
    """
    path = f"{cache_dir}/{dataset}/{name}.pkl"
    if not os.path.exists(path):
        return None
    try:
        size = os.path.getsize(path)
        if size < 1000:
            return None
        with open(path, "rb") as f:
            cache = pickle.load(f)
        if not cache:
            return None
        if expected_keys is not None:
            if not check_cache_consistency(
                expected_keys, set(cache.keys()), name=name, logger=logger
            ):
                return None
        return cache
    except Exception as e:
        if logger:
            logger.error(f"Error loading {name}: {e}")
        safe_remove(path, logger)
        return None


# ─── FAISS 中文路径处理 ───

_FAISS_PATH_MAPPING_CACHE: Dict[str, str] = {}


def safe_faiss_path(original_path: str, cache_root: str) -> str:
    """将含非 ASCII 字符的路径转为纯 ASCII 安全路径

    FAISS 的 C++ I/O 不支持中文路径。检测到非 ASCII 字符时，
    用 MD5 哈希生成安全文件名，存储在 cache_root/.faiss_safe/ 目录下，
    并将映射关系记录到 faiss_path_mapping.json。

    Args:
        original_path (`str`): 原始路径（可能含中文）
        cache_root (`str`): 缓存根目录

    Returns:
        `str`: ASCII 安全路径（无中文时返回原路径）
    """
    if not any(ord(c) > 127 for c in original_path):
        return original_path

    safe_name = hashlib.md5(original_path.encode("utf-8")).hexdigest()[:16]
    _, ext = os.path.splitext(original_path)

    safe_dir = os.path.join(cache_root, ".faiss_safe")
    os.makedirs(safe_dir, exist_ok=True)
    safe_path = os.path.join(safe_dir, safe_name + ext)

    _record_faiss_path_mapping(original_path, safe_path, cache_root)
    return safe_path


def faiss_path_exists(original_path: str, cache_root: str) -> bool:
    """检测 FAISS 文件是否存在，自动处理中文路径到安全路径的映射

    Args:
        original_path (`str`): 原始路径
        cache_root (`str`): 缓存根目录

    Returns:
        `bool`: True 表示文件存在
    """
    if not any(ord(c) > 127 for c in original_path):
        return os.path.exists(original_path)
    safe_path = safe_faiss_path(original_path, cache_root)
    return os.path.exists(safe_path)


def _record_faiss_path_mapping(orig: str, safe: str, cache_root: str):
    """记录中文路径 → 安全路径的映射到 JSON 字典

    确保同一文件在不同 session 中被映射到一致的 ASCII 路径。

    Args:
        orig (`str`): 原始中文路径
        safe (`str`): 映射后的 ASCII 路径
        cache_root (`str`): 缓存根目录
    """
    mapping_file = os.path.join(cache_root, "faiss_path_mapping.json")
    try:
        mapping = dict(_FAISS_PATH_MAPPING_CACHE)
        if os.path.exists(mapping_file):
            with open(mapping_file, "r", encoding="utf-8") as f:
                stored = json.load(f)
                for k, v in stored.items():
                    mapping.setdefault(k, v)
        mapping[orig] = safe
        os.makedirs(os.path.dirname(mapping_file), exist_ok=True)
        with open(mapping_file, "w", encoding="utf-8") as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)
        _FAISS_PATH_MAPPING_CACHE.clear()
        _FAISS_PATH_MAPPING_CACHE.update(mapping)
    except Exception:
        pass


SCHEMA_SKIP_FIELDS = {
    "name",
    "description",
    "properties",
    "label",
    "chunk id",
    "level",
}
