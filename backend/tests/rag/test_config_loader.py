"""配置加载器单元测试

测试策略：
- RetrievalTypeScale dataclass 的创建和行为
- retrieval_type_scales 在 RetrievalConfig 中的默认值
"""

from rag.config.config_loader import RetrievalTypeScale, RetrievalConfig


class TestRetrievalTypeScale:
    def test_default_values(self):
        scale = RetrievalTypeScale()
        assert scale.path1_scale == 1.0
        assert scale.path2_scale == 1.0
        assert scale.chunk_scale == 1.0

    def test_custom_values(self):
        scale = RetrievalTypeScale(path1_scale=1.5, path2_scale=0.5, chunk_scale=1.5)
        assert scale.path1_scale == 1.5
        assert scale.path2_scale == 0.5
        assert scale.chunk_scale == 1.5

    def test_partial_custom(self):
        scale = RetrievalTypeScale(path2_scale=0.3)
        assert scale.path1_scale == 1.0  # default
        assert scale.path2_scale == 0.3
        assert scale.chunk_scale == 1.0  # default


class TestRetrievalConfigTypeScales:
    def test_default_type_scales(self):
        config = RetrievalConfig()
        assert "micro" in config.retrieval_type_scales
        assert "macro" in config.retrieval_type_scales
        micro = config.retrieval_type_scales["micro"]
        assert micro.path1_scale == 1.5
        assert micro.path2_scale == 0.5
        assert micro.chunk_scale == 1.5
        macro = config.retrieval_type_scales["macro"]
        assert macro.path1_scale == 0.5
        assert macro.path2_scale == 1.5
        assert macro.chunk_scale == 0.5

    def test_unknown_type_fallback(self):
        """未知检索类型应返回 None（由调用方处理 fallback）"""
        config = RetrievalConfig()
        scale = config.retrieval_type_scales.get("unknown")
        assert scale is None
