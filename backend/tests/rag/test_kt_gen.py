"""KTBuilder / _validate_triple_format 单元测试

测试策略：
- _validate_triple_format 为纯函数，直接测试各边界情况
"""

import pytest

from rag.rag_models.constructor.kt_gen import _validate_triple_format


class TestValidateTripleFormat:
    """测试 _validate_triple_format 五元组校验函数"""

    def test_standard_3_element(self):
        """标准三元组 [头, 关系, 尾]"""
        result = _validate_triple_format(["Shawshank Redemption", "based on", "Rita Hayworth and Shawshank Redemption"])
        assert result is not None
        assert result["subject"] == "Shawshank Redemption"
        assert result["predicate"] == "based on"
        assert result["object"] == "Rita Hayworth and Shawshank Redemption"
        assert result["keywords"] == ""
        assert result["description"] == ""

    def test_5_element_full(self):
        """完整五元组 [头, 关系, 尾, 关键词, 描述]"""
        result = _validate_triple_format([
            "Shawshank Redemption", "based on", "Rita Hayworth and Shawshank Redemption",
            "adaptation, inspiration source", "The Shawshank Redemption is adapted from Stephen King's novella"
        ])
        assert result is not None
        assert result["keywords"] == "adaptation, inspiration source"
        assert result["description"] == "The Shawshank Redemption is adapted from Stephen King's novella"

    def test_4_element_with_keywords_only(self):
        """四元组 [头, 关系, 尾, 关键词]"""
        result = _validate_triple_format(["Entity A", "related_to", "Entity B", "keyword1, keyword2"])
        assert result is not None
        assert result["keywords"] == "keyword1, keyword2"
        assert result["description"] == ""

    def test_4_element_with_desc_only(self):
        """四元组 [头, 关系, 尾, 描述]"""
        result = _validate_triple_format(["Entity A", "related_to", "Entity B", "Some description"])
        assert result is not None
        assert result["keywords"] == "Some description"
        assert result["description"] == ""

    def test_5_element_empty_keywords_and_desc(self):
        """五元组但关键词和描述都为空字符串"""
        result = _validate_triple_format(["A", "rel", "B", "", ""])
        assert result is not None
        assert result["keywords"] == ""
        assert result["description"] == ""

    def test_5_element_keywords_empty_desc_present(self):
        """五元组关键词为空但有描述"""
        result = _validate_triple_format(["A", "rel", "B", "", "description text"])
        assert result is not None
        assert result["keywords"] == ""
        assert result["description"] == "description text"

    def test_less_than_3_elements(self):
        """不足 3 个元素应返回 None"""
        assert _validate_triple_format(["A"]) is None
        assert _validate_triple_format(["A", "rel"]) is None

    def test_empty_list(self):
        """空列表应返回 None"""
        assert _validate_triple_format([]) is None

    def test_none_input(self):
        """None 输入应返回 None（try 捕获异常）"""
        assert _validate_triple_format(None) is None

    def test_non_string_elements(self):
        """非字符串元素会被 str() 转换"""
        result = _validate_triple_format([123, 456, 789])
        assert result is not None
        assert result["subject"] == "123"
        assert result["predicate"] == "456"
        assert result["object"] == "789"

    def test_whitespace_stripped(self):
        """空格的 strip 处理"""
        result = _validate_triple_format(["  A  ", "  rel  ", "  B  ", "  kw  ", "  desc  "])
        assert result["subject"] == "A"
        assert result["predicate"] == "rel"
        assert result["object"] == "B"
        assert result["keywords"] == "kw"
        assert result["description"] == "desc"

    def test_more_than_5_elements(self):
        """超过 5 个元素时只取前 5 个（Python 切片自动截断）"""
        result = _validate_triple_format(["A", "rel", "B", "kw", "desc", "extra"])
        assert result is not None
        assert result["keywords"] == "kw"
        assert result["description"] == "desc"

    def test_empty_string_head(self):
        """头实体为空字符串"""
        result = _validate_triple_format(["", "rel", "B"])
        assert result is not None
        assert result["subject"] == ""

    def test_keywords_with_colon(self):
        """关键词包含冒号等特殊字符"""
        result = _validate_triple_format(["A", "rel", "B", "topic:subtopic, theme"])
        assert result["keywords"] == "topic:subtopic, theme"
