"""问题分解（GraphQ）：LLM 驱动的复杂问题拆解

功能：
- 将复杂多跳问题分解为 2-3 个聚焦的子问题
- 识别问题中涉及的 Schema 类型（nodes/relations/attributes）
- 支持中英文数据集

数据流：
  GraphQ.decompose(question, schema_path)
    → {
        "sub_questions": ["子问题1", "子问题2", ...],
        "involved_types": {"nodes": [...], "relations": [...], "attributes": [...]}
      }

  sub_questions 用于逐次检索合并上下文，
  involved_types 用于可选地 filter 检索结果。

注意：
  - 旧格式兼容：LLM 可能返回纯 list（无 involved_types），
    代码会转为新格式（involved_types 置空）。
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
        if self.config:
            if self.dataset_name == "anony_chs":
                return self.config.get_prompt_formatted(
                    "decomposition", "anony_chs", ontology=schema, question=question
                )
            else:
                return self.config.get_prompt_formatted(
                    "decomposition", "general", ontology=schema, question=question
                )
        else:
            if self.dataset_name == "anony_chs":
                return f"""
                你是一个专业的问题分解大师，请根据以下问题和图本体模式，将问题分解为2-3个子问题。
                要求：
                1. 每个子问题必须：
                   - 明确且专注于一个事实或关系，通过识别所有实体、关系和推理步骤
                   - 明确引用原始问题中的实体和关系
                   - 设计为检索最终答案所需的相关知识
                2. 对于简单问题（1-2跳），返回原始问题作为单个子问题
                3. 返回一个JSON数组，每个子问题是一个字符串。

                问题：{question}

                图本体模式：{schema}

                请返回一个JSON数组，每个子问题是一个字符串。
                示例：
                原始问题："智取生辰纲事件中，PERSON#1的策略为什么能够成功"
                子问题：
                [
                    {{"sub-question": "智取生辰纲中PERSON#1的策略是什么？"}},
                    {{"sub-question": "智取生辰纲中的PERSON、LOCATION有什么特殊属性？"}},
                ]
                如果是简单问题，返回原始问题作为单个子问题。
                原始问题："智取生辰纲事件中，PERSON#1是谁"
                子问题：
                [
                    {{"sub-question": "智取生辰纲事件中，PERSON#1是谁？"}}
                ]
                """
            else:
                return f"""
                You are a professional question decomposition expert specializing in multi-hop reasoning.
                Given the following schema and the question, decompose the complex question into 2-3 focused sub-questions.

                CRITICAL REQUIREMENTS:
                1. Each sub-question must be:
                   - Specific and focused on a single fact or relationship by identifing all entities, relationships, and reasoning steps needed
                   - Answerable independently with the given schema
                   - Explicitly reference entities and relations from the original question
                   - Designed to retrieve relevant knowledge for the final answer

                2. For simple questions (1-2 hop), return the original question as a single sub-question
                3. Return a JSON array, each sub-question is a string.

                Graph Schema:
                {schema}

                Question: {question}

                Example for complex question:
                Original: "Which film has the director died earlier, Ethnic Notions or Gordon Of Ghost City?"
                Sub-questions:
                [
                    {{"sub-question": "Who is the director of Ethnic Notions?"}},
                    {{"sub-question": "Who is the director of Gordon Of Ghost City?"}},
                    {{"sub-question": "When did the director of Ethnic Notions die?"}},
                    {{"sub-question": "When did the director of Gordon Of Ghost City die?"}}
                ]

                Example for simple question:
                Original: "What is the capital of France?"
                Sub-questions:
                [
                    {{"sub-question": "What is the capital of France?"}}
                ]
                """

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

        # Ensure backward compatibility - if old format, convert to new format
        if isinstance(content, list):
            content = {
                "sub_questions": content,
                "involved_types": {"nodes": [], "relations": [], "attributes": []},
            }

        return content
