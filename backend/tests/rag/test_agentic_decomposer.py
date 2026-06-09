"""GraphQ 问题分解器单元测试

测试策略：
- backward compatibility：旧格式（字符串列表）→ 新格式（dict with search_query/type）
- _validate_triple_format 已在 test_kt_gen.py 中覆盖
"""

import json

from rag.rag_models.retrieval.agentic_decomposer import GraphQ


class TestSubQuestionBackwardCompat:
    """测试子问题格式向后兼容处理的辅助逻辑（decompose 内部逻辑的隔离测试）"""

    def _simulate_decompose_patch(self, content: dict) -> dict:
        """模拟 agentic_decomposer.py:197-204 的向后兼容逻辑"""
        sub_qs = content.get("sub_questions", [])
        for i, sq in enumerate(sub_qs):
            if isinstance(sq, str):
                sub_qs[i] = {"sub-question": sq}
                sq = sub_qs[i]
            if "search_query" not in sq:
                sq["search_query"] = sq.get("sub-question", "")
            if "type" not in sq:
                sq["type"] = "micro"
        content["sub_questions"] = sub_qs
        return content

    def test_string_list_conversion(self):
        """字符串列表应转换为 dict 列表"""
        content = {
            "sub_questions": ["What is A?", "What is B?"],
            "involved_types": {},
        }
        result = self._simulate_decompose_patch(content)
        for sq in result["sub_questions"]:
            assert isinstance(sq, dict)
            assert "sub-question" in sq
            assert "search_query" in sq
            assert "type" in sq

    def test_mixed_list(self):
        """混合字符串和 dict 的列表应正确处理"""
        content = {
            "sub_questions": [
                "Old style question",
                {"sub-question": "New style", "type": "micro"},
            ],
            "involved_types": {},
        }
        result = self._simulate_decompose_patch(content)
        assert isinstance(result["sub_questions"][0], dict)
        assert result["sub_questions"][0]["search_query"] == "Old style question"
        assert result["sub_questions"][1].get("search_query") == "New style"
        assert result["sub_questions"][0]["type"] == "micro"

    def test_dict_without_search_query(self):
        """已有 dict 格式但没有 search_query 时应自动补全"""
        content = {
            "sub_questions": [
                {"sub-question": "What is A?"},
            ],
            "involved_types": {},
        }
        result = self._simulate_decompose_patch(content)
        assert result["sub_questions"][0]["search_query"] == "What is A?"
        assert result["sub_questions"][0]["type"] == "micro"

    def test_dict_with_existing_search_query(self):
        """已有 search_query 和 type 不应覆盖"""
        content = {
            "sub_questions": [
                {
                    "sub-question": "What is A?",
                    "search_query": "A definition",
                    "type": "micro",
                },
            ],
            "involved_types": {},
        }
        result = self._simulate_decompose_patch(content)
        assert result["sub_questions"][0]["search_query"] == "A definition"

    def test_empty_sub_questions(self):
        content = {"sub_questions": [], "involved_types": {}}
        result = self._simulate_decompose_patch(content)
        assert result["sub_questions"] == []

    def test_empty_string_sub_question(self):
        """空字符串也应正确转换"""
        content = {"sub_questions": [""], "involved_types": {}}
        result = self._simulate_decompose_patch(content)
        assert result["sub_questions"][0]["sub-question"] == ""
        assert result["sub_questions"][0]["search_query"] == ""

    def test_old_format_list(self):
        """旧格式纯列表（无 involved_types）"""
        old_data = [
            {"sub-question": "Old sub Q1"},
            {"sub-question": "Old sub Q2"},
        ]
        content = {
            "sub_questions": old_data,
            "involved_types": {"nodes": [], "relations": [], "attributes": []},
        }
        result = self._simulate_decompose_patch(content)
        for sq in result["sub_questions"]:
            assert "search_query" in sq
            assert sq["search_query"] == sq.get("sub-question", "")
            assert sq["type"] == "micro"
