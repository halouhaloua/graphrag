"""
OCR识别服务
提供常见场景OCR和复杂竖排繁体文本OCR两种能力
列重构支持两种策略（自动判断横排/竖排方向）：
    - dbscan : 自适应 DBSCAN（默认，鲁棒性好）
    - gap    : 基于间隙分割（速度快，适合版式规整图像）
"""
import fitz
import asyncio
import numpy as np
from PIL import Image
from sklearn.cluster import DBSCAN
import pathlib

# ========== 策略常量 ==========
METHOD_DBSCAN = "dbscan"
METHOD_GAP = "gap"
detection_model = pathlib.Path(__file__).parent.parent.parent.parent / ".paddlex/official_models/PP-OCRv5_server_det_safetensors"
recognition_model = pathlib.Path(__file__).parent.parent.parent.parent / ".paddlex/official_models/PP-OCRv5_server_rec_safetensors"

# ========== PP-OCRv5 引擎（单例） ==========

_ocr_engine = None

def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is not None:
        return _ocr_engine
    from paddleocr import PaddleOCR
    import torch
    _device = "gpu" if torch.cuda.is_available() else "cpu"
    from loguru import logger
    logger.info(f"PP-OCRv5 engine using device: {_device}")
    _ocr_engine = PaddleOCR(
        text_detection_model_dir=detection_model,
        text_recognition_model_dir=recognition_model,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        engine="transformers",
        device=_device
    )
    return _ocr_engine

# _get_ocr_engine()

# ========== 竖排文本列重构 - DBSCAN 版（自适应） ==========

def _reconstruct_vertical_layout_dbscan(rec_texts: list, dt_polys: list,
                                        is_vertical: bool = True) -> str:
    """
    自适应 DBSCAN 列聚类 + 列内上→下排序
    竖排时列间右→左排序，横排时列间左→右排序
    返回原文排版（每列一行）
    """
    lines = []
    for text, box in zip(rec_texts, dt_polys):
        cx = (box[0][0] + box[2][0]) / 2
        cy = (box[0][1] + box[2][1]) / 2
        lines.append({"cx": cx, "cy": cy, "text": text.strip()})

    if not lines:
        return ""

    # 自适应 eps 估算
    x_vals = np.array([p["cx"] for p in lines])
    if len(x_vals) > 1:
        sorted_x = np.sort(x_vals)
        diffs = np.diff(sorted_x)
        median_diff = np.median(diffs)
        large_diffs = diffs[diffs > median_diff * 1.2]
        if len(large_diffs) > 0:
            eps = float(np.clip(np.mean(large_diffs) * 0.55, 15, 50))
        else:
            eps = float(np.clip(median_diff * 2.0, 15, 50))
    else:
        eps = 20.0

    db = DBSCAN(eps=eps, min_samples=2)
    labels = db.fit_predict(x_vals.reshape(-1, 1))

    # 噪声点就近归入现有列
    unique_labs = set(labels)
    if -1 in unique_labs and len(unique_labs) > 1:
        cluster_centers = {}
        for lab in unique_labs - {-1}:
            cluster_centers[lab] = np.mean(x_vals[labels == lab])

        noise_idx = np.where(labels == -1)[0]
        for idx in noise_idx:
            if not cluster_centers:
                break
            nearest_lab = min(cluster_centers, key=lambda l: abs(x_vals[idx] - cluster_centers[l]))
            if abs(x_vals[idx] - cluster_centers[nearest_lab]) <= eps * 1.5:
                labels[idx] = nearest_lab

    # 构建列分组
    col_groups = {}
    for idx, lab in enumerate(labels):
        if lab == -1:
            lab = max(labels) + 1
            labels[idx] = lab
        col_groups.setdefault(int(lab), []).append(lines[idx])

    # 列排序：竖排右→左，横排左→右；列内：上→下
    cols = sorted(col_groups.values(), key=lambda g: np.mean([i["cx"] for i in g]),
                  reverse=is_vertical)
    final_cols = [sorted(col, key=lambda x: x["cy"]) for col in cols]

    ancient_text = ""
    for col in final_cols:
        col_txt = "".join([i["text"] for i in col])
        ancient_text += col_txt + "\n"
    return ancient_text

# ========== 竖排文本列重构 - 间隙分割版 ==========

def _reconstruct_vertical_layout_gap(rec_texts: list, dt_polys: list,
                                     gap_factor: float = 2.5,
                                     is_vertical: bool = True) -> str:
    """
    基于 x 坐标间隙的列重构（无聚类算法）
    - 适用于版式规整的古籍（列内 x 偏移小，列间有明显空隙）
    - gap_factor: 间隙阈值倍数，默认 2.5
    竖排时列间右→左排序，横排时列间左→右排序
    返回原文排版
    """
    lines = []
    for text, box in zip(rec_texts, dt_polys):
        cx = (box[0][0] + box[2][0]) / 2
        cy = (box[0][1] + box[2][1]) / 2
        lines.append({"cx": cx, "cy": cy, "text": text.strip()})

    if not lines:
        return ""

    sorted_lines = sorted(lines, key=lambda p: p["cx"])
    xs = np.array([p["cx"] for p in sorted_lines])

    if len(xs) <= 1:
        col = "".join(p["text"] for p in sorted_lines)
        return col + "\n"

    gaps = np.diff(xs)
    median_gap = np.median(gaps) if len(gaps) > 0 else 0
    if median_gap == 0:
        col = "".join(p["text"] for p in sorted_lines)
        return col + "\n"

    threshold = median_gap * gap_factor

    split_indices = np.where(gaps > threshold)[0] + 1
    split_indices = np.concatenate([[0], split_indices, [len(sorted_lines)]])

    cols = []
    for i in range(len(split_indices) - 1):
        col_lines = sorted_lines[split_indices[i]:split_indices[i + 1]]
        if col_lines:
            cols.append(col_lines)

    cols = sorted(cols, key=lambda g: np.mean([p["cx"] for p in g]),
                  reverse=is_vertical)
    final_cols = [sorted(col, key=lambda x: x["cy"]) for col in cols]

    ancient_text = ""
    for col in final_cols:
        col_txt = "".join([p["text"] for p in col])
        ancient_text += col_txt + "\n"
    return ancient_text

# ========== 文字方向检测 ==========

def _is_vertical_layout(dt_polys: list) -> bool:
    """判断文字方向。True=竖排，False=横排。

    原理：竖排文本的检测框是「高>宽」（单个竖列窄而长），
    横排文本的检测框是「宽>高」（整行文字宽而扁）。
    统计大部分框（>50%）的高宽比来判断。
    """
    if not dt_polys:
        return True
    vertical_count = 0
    for box in dt_polys:
        w = max(box[1][0] - box[0][0], box[2][0] - box[3][0])
        h = max(box[2][1] - box[1][1], box[3][1] - box[0][1])
        if h > w * 1.5:
            vertical_count += 1
    return vertical_count > len(dt_polys) // 2


# ========== 统一列重构入口 ==========

def _reconstruct_vertical_layout(rec_texts: list, dt_polys: list,
                                 method: str = METHOD_DBSCAN) -> str:
    """根据 method 选择列重构策略，自动检测文字方向"""
    is_vertical = _is_vertical_layout(dt_polys)
    if method == METHOD_GAP:
        return _reconstruct_vertical_layout_gap(rec_texts, dt_polys, is_vertical=is_vertical)
    return _reconstruct_vertical_layout_dbscan(rec_texts, dt_polys, is_vertical=is_vertical)

# ========== 图像 OCR（支持策略选择） ==========

def _ocr_image(image, method: str = METHOD_DBSCAN) -> str:
    """
    对单张图片执行 PP-OCRv5 识别 + 竖排文本重构
    image: 文件路径(str) 或 PIL Image
    method: 'dbscan' 或 'gap'
    返回识别后的文本
    """
    ocr = _get_ocr_engine()
    result = ocr.predict(image)
    for res in result:
        rec_texts = dict(res)["rec_texts"]
        dt_polys = dict(res)["dt_polys"]
        if rec_texts:
            return _reconstruct_vertical_layout(rec_texts, dt_polys, method)
    return ""

# ========== PDF 转换 ==========

def _pdf_to_images(pdf_path: str, dpi: int = 300) -> list:
    """将 PDF 每页转换为 PIL Image 列表"""
    doc = fitz.open(pdf_path)
    images = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        images.append(img)
    doc.close()
    return images

# ========== 复杂竖排 OCR 同步实现 ==========

def _complex_ocr_sync(file_path: str, file_ext: str,
                      method: str = METHOD_DBSCAN) -> str:
    """复杂竖排繁体文本OCR 同步实现"""
    ext = file_ext.lower()
    if ext in ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'):
        return _ocr_image(file_path, method=method)
    elif ext == '.pdf':
        images = _pdf_to_images(file_path)
        parts = []
        for img in images:
            text = _ocr_image(img, method=method)
            if text:
                parts.append(text)
        return '\n'.join(parts)
    else:
        return _common_ocr_sync(file_path, file_ext)

# ========== 复杂竖排 OCR 异步入口 ==========

async def complex_ocr(file_path: str, file_ext: str,
                      method: str = METHOD_DBSCAN) -> str:
    """复杂竖排繁体文本OCR 异步入口（支持 strategy 参数）"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _complex_ocr_sync, file_path, file_ext, method
    )

# ========== 常见场景OCR（标准文本提取） ==========

def _common_ocr_sync(file_path: str, file_ext: str) -> str:
    """标准文本提取：PyPDF2/pdfplumber(PDF), python-docx(Word), utf-8(txt/md)"""
    ext = file_ext.lower()
    try:
        if ext in ('.txt', '.md'):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        elif ext == '.pdf':
            try:
                import PyPDF2
                text = ''
                with open(file_path, 'rb') as f:
                    for page in PyPDF2.PdfReader(f).pages:
                        text += page.extract_text() + '\n'
                return text
            except ImportError:
                import pdfplumber
                text = ''
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        text += page.extract_text() + '\n'
                return text
        elif ext in ('.doc', '.docx'):
            import docx
            return '\n'.join(p.text for p in docx.Document(file_path).paragraphs)
    except Exception as e:
        return f"[OCR Error: {e}]"
    return ''

async def common_ocr(file_path: str, file_ext: str) -> str:
    """常见场景OCR 异步入口"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _common_ocr_sync, file_path, file_ext)