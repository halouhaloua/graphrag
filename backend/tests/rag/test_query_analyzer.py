"""QueryAnalyzer 模块单元测试

测试策略：
- _parse_analysis / _fallback_analysis / _parse_ircot_response 为纯函数，直接测试
- analyze() 依赖 LLM 调用，通过 monkeypatch mock
"""

import json
from unittest.mock import MagicMock

from rag.rag_models.retrieval.query_analyzer import QueryAnalyzer


class TestParseAnalysis:
    def setup_method(self):
        self.analyzer = QueryAnalyzer(dataset_name="test")

    def test_parse_valid_response(self):
        """测试解析标准 JSON 格式"""
        resp = json.dumps(
            {
                "low_level_keywords": ["beekeeper", "hive"],
                "high_level_keywords": ["environmental impact"],
                "sub_questions": [
                    {"sub-question": "What do beekeepers do?"},
                    {"sub-question": "How do pesticides affect bees?"},
                ],
            }
        )
        result = self.analyzer._parse_analysis(resp, "What do beekeepers do?")
        assert result["low_level_keywords"] == ["beekeeper", "hive"]
        assert result["high_level_keywords"] == ["environmental impact"]
        assert len(result["sub_questions"]) == 2

    def test_parse_backward_compat_list(self):
        """测试解析旧格式（子问题列表，无 dict 包装）"""
        resp = json.dumps(
            [
                {"sub-question": "Q1"},
                {"sub-question": "Q2"},
            ]
        )
        result = self.analyzer._parse_analysis(resp, "test question")
        assert len(result["sub_questions"]) == 2

    def test_parse_fallback_on_garbage(self):
        """测试 LLM 返回非 JSON 时 fallback"""
        result = self.analyzer._parse_analysis(
            "This is not JSON at all!!!", "real question"
        )
        assert result["sub_questions"][0]["sub-question"] == "real question"

    def test_parse_empty_low_level(self):
        """测试关键词为空的情况"""
        resp = json.dumps(
            {
                "low_level_keywords": [],
                "high_level_keywords": [],
                "sub_questions": [{"sub-question": "Test question?"}],
            }
        )
        result = self.analyzer._parse_analysis(resp, "some question")
        assert result["low_level_keywords"] == []
        assert result["high_level_keywords"] == []

    def test_parse_sub_questions_with_str_format(self):
        """测试子问题为字符串列表的格式"""
        resp = json.dumps(
            {
                "low_level_keywords": ["kw"],
                "high_level_keywords": [],
                "sub_questions": ["Q1?", "Q2?"],
            }
        )
        result = self.analyzer._parse_analysis(resp, "some question")
        assert len(result["sub_questions"]) == 2
        assert result["sub_questions"][0]["sub-question"] == "Q1?"


class TestFallbackAnalysis:
    def setup_method(self):
        self.analyzer = QueryAnalyzer(dataset_name="test")

    def test_fallback_has_question(self):
        """测试 fallback 返回原始问题作为子问题"""
        result = self.analyzer._fallback_analysis("What is beekeeping?")
        assert len(result["sub_questions"]) == 1
        assert result["sub_questions"][0]["sub-question"] == "What is beekeeping?"

    def test_fallback_empty_question(self):
        result = self.analyzer._fallback_analysis("")
        assert len(result["sub_questions"]) == 1

    def test_fallback_high_level_empty(self):
        """fallback 时 high_level_keywords 为空"""
        result = self.analyzer._fallback_analysis("test")
        assert result["high_level_keywords"] == []


class TestParseIrcotResponse:
    def setup_method(self):
        self.analyzer = QueryAnalyzer(dataset_name="test")

    def test_parse_final_answer(self):
        text = """I have enough information to answer.
        So the answer is: Beekeepers manage bee colonies."""
        result = self.analyzer._parse_ircot_response(text)
        assert result["final_answer"] is not None
        assert "Beekeepers" in result["final_answer"]
        assert result["new_query"] is None

    def test_parse_new_query_and_keywords(self):
        text = """I need more information to answer this question.

        The new query is: How do pesticides affect honey production?
        The new low-level keywords: pesticide, honey, bee
        The new high-level keywords: environmental impact, agriculture"""
        result = self.analyzer._parse_ircot_response(text)
        assert result["final_answer"] is None
        assert result["new_query"] == "How do pesticides affect honey production?"
        assert "pesticide" in result["low_level_keywords"]
        assert "environmental impact" in result["high_level_keywords"]

    def test_parse_keywords_with_colon_in_values(self):
        text = """The new query is: test
        The new low-level keywords: kw1, kw2, kw3
        The new high-level keywords: topic:subtopic, topic2"""
        result = self.analyzer._parse_ircot_response(text)
        assert "kw1" in result["low_level_keywords"]
        # high_level contains "topic:subtopic" - colon is in the value, not a separator
        assert "topic:subtopic" in result["high_level_keywords"]

    def test_parse_missing_query(self):
        """LLM 没有输出 new_query 时"""
        text = "Some reasoning without clear markers."
        result = self.analyzer._parse_ircot_response(text)
        assert result["new_query"] is None
        assert result["final_answer"] is None

    def test_parse_json_sufficient(self):
        """测试新 JSON 格式（sufficient=true）"""
        text = json.dumps({
            "sufficient": True,
            "final_answer": "The CEO of Tesla is Elon Musk."
        })
        result = self.analyzer._parse_ircot_response(text)
        assert result["final_answer"] == "The CEO of Tesla is Elon Musk."
        assert result["new_query"] is None

    def test_parse_json_insufficient(self):
        """测试新 JSON 格式（sufficient=false）"""
        text = json.dumps({
            "sufficient": False,
            "refined_query": "What is the population of New York City?",
            "low_level_keywords": ["New York City", "population"],
            "high_level_keywords": ["urban demographics", "city comparison"],
        })
        result = self.analyzer._parse_ircot_response(text)
        assert result["final_answer"] is None
        assert result["new_query"] == "What is the population of New York City?"
        assert "New York City" in result["low_level_keywords"]
        assert "urban demographics" in result["high_level_keywords"]


class TestAnalyzeWithMock:
    def test_analyze_calls_llm_and_parses(self):
        """mock LLM 调用，验证 analyze 流程"""
        mock_response = json.dumps(
            {
                "low_level_keywords": ["beekeeper", "hive"],
                "high_level_keywords": ["sustainability"],
                "sub_questions": [
                    {"sub-question": "What tools do beekeepers use?"},
                ],
            }
        )
        analyzer = QueryAnalyzer(dataset_name="test")
        analyzer.llm_client = MagicMock()
        analyzer.llm_client.call_api.return_value = mock_response

        result = analyzer.analyze("What equipment do beekeepers use?")
        assert result["low_level_keywords"] == ["beekeeper", "hive"]
        assert result["high_level_keywords"] == ["sustainability"]
        assert len(result["sub_questions"]) == 1
        analyzer.llm_client.call_api.assert_called_once()

    def test_analyze_llm_failure_fallback(self):
        """LLM 异常时回退到 fallback"""
        analyzer = QueryAnalyzer(dataset_name="test")
        analyzer.llm_client = MagicMock()
        analyzer.llm_client.call_api.side_effect = Exception("API Error")

        result = analyzer.analyze("What is beekeeping?")
        assert len(result["sub_questions"]) == 1
        assert result["sub_questions"][0]["sub-question"] == "What is beekeeping?"

    def test_analyze_empty_question(self):
        analyzer = QueryAnalyzer(dataset_name="test")
        result = analyzer.analyze("")
        assert len(result["sub_questions"]) == 1
