"""
OCR 模块纯函数单元测试
"""

from rag.file_manager.ocr import (
    BATCH_SIZE,
    COMPLEX_OCR_BATCH,
    MAX_IMAGE_PX,
    METHOD_DBSCAN,
    METHOD_GAP,
    _is_garbled,
    _is_vertical_layout,
    _reconstruct_horizontal_layout,
    _reconstruct_vertical_layout,
    _reconstruct_vertical_layout_dbscan,
    _reconstruct_vertical_layout_gap,
)


def box(x1, y1, x2, y2, x3, y3, x4, y4):
    """Helper to create a detection box [top-left, top-right, bottom-right, bottom-left]"""
    return [(x1, y1), (x2, y2), (x3, y3), (x4, y4)]


class TestVerticalLayoutDetection:
    def test_empty_boxes_defaults_to_vertical(self):
        assert _is_vertical_layout([]) is True

    def test_horizontal_boxes(self):
        boxes = [box(0, 0, 200, 0, 200, 30, 0, 30)] * 10
        assert _is_vertical_layout(boxes) is False

    def test_vertical_boxes(self):
        boxes = [box(0, 0, 30, 0, 30, 200, 0, 200)] * 10
        assert _is_vertical_layout(boxes) is True

    def test_mixed_boxes_majority_vertical(self):
        vert = [box(0, 0, 30, 0, 30, 200, 0, 200)] * 6
        horz = [box(0, 0, 200, 0, 200, 30, 0, 30)] * 4
        assert _is_vertical_layout(vert + horz) is True

    def test_mixed_boxes_majority_horizontal(self):
        vert = [box(0, 0, 30, 0, 30, 200, 0, 200)] * 4
        horz = [box(0, 0, 200, 0, 200, 30, 0, 30)] * 6
        assert _is_vertical_layout(vert + horz) is False


class TestReconstructVerticalLayoutDbscan:
    def test_empty_returns_empty(self):
        assert _reconstruct_vertical_layout_dbscan([], []) == ""

    def test_multiple_columns_vertical(self):
        texts = ["col2a", "col2b", "col1a", "col1b"]
        polys = [
            box(200, 0, 230, 0, 230, 50, 200, 50),
            box(200, 60, 230, 60, 230, 110, 200, 110),
            box(0, 0, 30, 0, 30, 50, 0, 50),
            box(0, 60, 30, 60, 30, 110, 0, 110),
        ]
        result = _reconstruct_vertical_layout_dbscan(texts, polys, is_vertical=True)
        lines = result.strip().split('\n')
        assert len(lines) >= 2
        assert "col2" in lines[0]
        assert "col1" in lines[1]


class TestReconstructVerticalLayoutGap:
    def test_empty_returns_empty(self):
        assert _reconstruct_vertical_layout_gap([], []) == ""

    def test_two_columns_vertical(self):
        texts = ["col2a", "col2b", "col1a", "col1b"]
        polys = [
            box(200, 0, 230, 0, 230, 50, 200, 50),
            box(210, 60, 240, 60, 240, 110, 210, 110),
            box(0, 0, 30, 0, 30, 50, 0, 50),
            box(10, 60, 40, 60, 40, 110, 10, 110),
        ]
        result = _reconstruct_vertical_layout_gap(texts, polys, is_vertical=True)
        lines = result.strip().split('\n')
        assert len(lines) >= 2
        assert "col2" in lines[0]
        assert "col1" in lines[1]


class TestReconstructHorizontalLayout:
    def test_empty_returns_empty(self):
        assert _reconstruct_horizontal_layout([], []) == ""

    def test_single_text(self):
        assert _reconstruct_horizontal_layout(
            ["hello"], [[(0, 0), (100, 0), (100, 20), (0, 20)]]
        ) == "hello"

    def test_single_column_two_rows(self):
        assert _reconstruct_horizontal_layout(
            ["hello", "world"],
            [[(0, 0), (100, 0), (100, 20), (0, 20)],
             [(0, 50), (100, 50), (100, 70), (0, 70)]],
        ) == "hello world"

    def test_dual_column(self):
        assert _reconstruct_horizontal_layout(
            ["left1", "right1", "left2", "right2", "left3", "right3"],
            [box(0, 0, 80, 0, 80, 20, 0, 20),
             box(200, 0, 280, 0, 280, 20, 200, 20),
             box(0, 50, 80, 50, 80, 70, 0, 70),
             box(200, 50, 280, 50, 280, 70, 200, 70),
             box(0, 100, 80, 100, 80, 120, 0, 120),
             box(200, 100, 280, 100, 280, 120, 200, 120)],
        ) == "left1 left2 left3\nright1 right2 right3"

    def test_mixed_single_then_dual(self):
        assert _reconstruct_horizontal_layout(
            ["标题跨栏", "摘要跨栏",
             "左一", "右一", "左二", "右二", "左三", "右三"],
            [box(20, 10, 180, 10, 180, 30, 20, 30),
             box(20, 40, 180, 40, 180, 60, 20, 60),
             box(0, 80, 60, 80, 60, 100, 0, 100),
             box(140, 80, 200, 80, 200, 100, 140, 100),
             box(0, 110, 60, 110, 60, 130, 0, 130),
             box(140, 110, 200, 110, 200, 130, 140, 130),
             box(0, 140, 60, 140, 60, 160, 0, 160),
             box(140, 140, 200, 140, 200, 160, 140, 160)],
        ) == "标题跨栏 摘要跨栏\n左一 左二 左三\n右一 右二 右三"

    def test_skips_empty_text(self):
        assert _reconstruct_horizontal_layout(
            ["hello", "", "world"],
            [[(0, 0), (100, 0), (100, 20), (0, 20)],
             [(0, 10), (100, 10), (100, 30), (0, 30)],
             [(0, 50), (100, 50), (100, 70), (0, 70)]],
        ) == "hello world"


class TestReconstructVerticalLayout:
    def test_vertical_dispatches_dbscan(self):
        texts = ["v1", "v2"]
        polys = [box(0, 0, 30, 0, 30, 200, 0, 200)] * 2
        result = _reconstruct_vertical_layout(texts, polys, method=METHOD_DBSCAN)
        assert "v1" in result and "v2" in result

    def test_vertical_dispatches_gap(self):
        texts = ["v1", "v2"]
        polys = [box(0, 0, 30, 0, 30, 200, 0, 200)] * 2
        result = _reconstruct_vertical_layout(texts, polys, method=METHOD_GAP)
        assert "v1" in result and "v2" in result

    def test_horizontal_dispatches_horizontal_layout(self):
        texts = ["hello", "world"]
        polys = [[(0, 0), (100, 0), (100, 20), (0, 20)]] * 2
        result = _reconstruct_vertical_layout(texts, polys)
        assert result == "hello world"


class TestConstants:
    def test_ocr_batch_defined(self):
        assert isinstance(COMPLEX_OCR_BATCH, int)
        assert COMPLEX_OCR_BATCH > 0

    def test_max_image_px_defined(self):
        assert isinstance(MAX_IMAGE_PX, int)
        assert MAX_IMAGE_PX > 0

    def test_batch_size_defined(self):
        assert isinstance(BATCH_SIZE, int)
        assert BATCH_SIZE > 0


class TestIsGarbled:
    def test_empty_is_garbled(self):
        assert _is_garbled("") is True

    def test_short_text_is_garbled(self):
        assert _is_garbled("ab") is True

    def test_normal_text_not_garbled(self):
        assert _is_garbled("Hello World 你好世界") is False

    def test_all_printable_not_garbled(self):
        assert _is_garbled("printable text with numbers 123 and punct!") is False

    def test_mostly_control_chars_is_garbled(self):
        assert _is_garbled("\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c") is True

    def test_mixed_garbled_with_threshold(self):
        # 控制字符占多数 → garbled
        text = "\x00" * 20 + "hello"
        assert _is_garbled(text) is True

    def test_threshold_edge(self):
        # 刚好 50% 可打印 → threshold=0.5 时不算 garbled（需要 < 0.5）
        text = "\x00" * 10 + "a" * 10
        assert _is_garbled(text) is False

    def test_newline_and_tab_not_garbled(self):
        assert _is_garbled("line1\n\tline2\n\tline3") is False
