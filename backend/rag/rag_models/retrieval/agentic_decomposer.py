"""问题分解（GraphQ）：LLM 驱动的复杂问题拆解

功能：
- 将复杂多跳问题分解为 2-3 个聚焦的子问题
- 每个子问题带 search_query（检索用关键词）和 type（micro/macro）
- 识别问题中涉及的 Schema 类型（nodes/relations/attributes）
- 支持中英文数据集

数据流：
  GraphQ.decompose(question, schema_path)
    → {
        "sub_questions": [
          {"sub-question": "...", "search_query": "...", "type": "micro|macro"},
          ...
        ],
        "involved_types": {"nodes": [...], "relations": [...], "attributes": [...]}
      }

  sub_questions 用于逐次检索合并上下文（检索用 search_query），
  involved_types 用于可选地 filter 检索结果。

注意：
  - 旧格式兼容：LLM 可能返回纯 list（无 involved_types），
    代码会转为新格式（involved_types 置空）。
  - 旧格式子问题（纯字符串 / 无 search_query/type）自动补全。
"""

import json
import json_repair
from rag.utils import call_llm_api

try:
    from rag.config import get_config
except ImportError:
    get_config = None


class GraphQ:
    """问题分解器

    使用 LLM 将复杂问题拆解为多个聚焦的子问题（multi-hop decomposition），
    并识别涉及的实体/关系类型。

    Attributes:
        dataset_name (`str`): 数据集名称，决定提示词语言和模板
        config: 配置对象（提供 prompt template）
        llm_client (`LLMCompletionCall`): 同步 LLM 调用客户端
        schema_data: 图 schema 数据（可选）
    """

    def __init__(self, dataset_name, config=None, schema_data=None):
        """初始化 GraphQ

        Args:
            dataset_name (`str`): 数据集名称
            config: 配置对象（可选，默认从全局获取）
            schema_data: 图本体 schema（可选）
        """
        if config is None and get_config is not None:
            try:
                self.config = get_config()
            except Exception:
                self.config = None
        else:
            self.config = config
        self.llm_client = call_llm_api.LLMCompletionCall()
        self.dataset_name = dataset_name
        self.schema_data = schema_data

    def read_schema(self, schema_path: str = "") -> str:
        """读取图本体 schema

        Args:
            schema_path (`str`): schema 文件路径（优先使用 schema_data）

        Returns:
            `str`: JSON 格式的 schema 字符串
        """
        if self.schema_data:
            return json.dumps(self.schema_data, ensure_ascii=False)
        with open(schema_path, "r") as f:
            schema = f.read()
        return schema

    def prompt_format(self, schema: str, question: str) -> str:
        """构建问题分解的提示词

        优先使用 config 的 prompt template，
        fallback 为硬编码的双语模板。

        Args:
            schema (`str`): 图本体 schema JSON 字符串
            question (`str`): 用户原始问题

        Returns:
            `str`: 完整 LLM 提示词
        """
        return self.config.get_prompt_formatted(
            "decomposition", "general", ontology=schema, question=question
        )


    def decompose(self, question: str, schema_path: str) -> dict:
        """执行问题分解

        调用 LLM 对问题进行分解，解析返回的 JSON。

        Args:
            question (`str`): 用户原始问题
            schema_path (`str`): 图本体 schema 文件路径

        Returns:
            `dict`:
                - "sub_questions": List[str] — 分解后的子问题列表
                - "involved_types": dict — {"nodes": [], "relations": [], "attributes": []}
        """
        schema = self.read_schema(schema_path)
        prompt = self.prompt_format(schema, question)
        response = self.llm_client.call_api(prompt)
        content = json_repair.loads(response)

        # Ensure backward compatibility
        if content is None:
            content = {"sub_questions": [], "involved_types": {"nodes": [], "relations": [], "attributes": []}}
        elif isinstance(content, list):
            content = {
                "sub_questions": content,
                "involved_types": {"nodes": [], "relations": [], "attributes": []},
            }

        # Ensure each sub-question has search_query and type (backward compatibility)
        sub_qs = content.get("sub_questions", [])
        for i, sq in enumerate(sub_qs):
            if isinstance(sq, str):
                sq = {"sub-question": sq}
                sub_qs[i] = sq
            if "search_query" not in sq:
                sq["search_query"] = sq.get("sub-question", "")
            if "type" not in sq:
                sq["type"] = "micro"

        return content
