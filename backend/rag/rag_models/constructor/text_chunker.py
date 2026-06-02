"""基于 langchain 的文本分块模块

使用 langchain RecursiveCharacterTextSplitter 替代自实现的分块逻辑，
支持可配置的 tokenizer 和分隔符，输出 chunk 数量和 token 统计日志。
"""

from typing import List, Optional, Tuple

from loguru import logger

LANGCHAIN_AVAILABLE = False
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    LANGCHAIN_AVAILABLE = True
except ImportError:
    RecursiveCharacterTextSplitter = None


def _build_splitter(
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    encoding_name: str = "cl100k_base",
) -> Optional["RecursiveCharacterTextSplitter"]:
    """创建 langchain RecursiveCharacterTextSplitter

    使用 tiktoken 作为 token 计数函数，支持中英文分隔符。
    返回 None 表示 langchain 不可用。
    """
    if not LANGCHAIN_AVAILABLE:
        return None

    import tiktoken

    def _token_len(text: str) -> int:
        try:
            return len(tiktoken.get_encoding(encoding_name).encode(text))
        except Exception:
            return len(text)

    separators = [
        "\n\n",
        "\n",
        "。",
        "！",
        "？",
        "；",
        "，",
        " ",
        "",
    ]
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=_token_len,
        separators=separators,
    )


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    encoding_name: str = "cl100k_base",
) -> Tuple[List[str], int]:
    """对文本进行分块

    Args:
        text: 原始文本
        chunk_size: 每块的最大 token 数
        chunk_overlap: 块间重叠 token 数
        encoding_name: tiktoken 编码名称

    Returns:
        (chunks列表, 总token数)

    日志输出：
    - 分块总数
    - 每个 chunk 的 token 数和字符数
    - 总 token 数
    - 平均每块 token 数
    """
    import tiktoken

    try:
        encoding = tiktoken.get_encoding(encoding_name)
    except Exception:
        logger.warning(
            f"Unknown tiktoken encoding '{encoding_name}', falling back to 'cl100k_base'"
        )
        encoding = tiktoken.get_encoding("cl100k_base")

    total_raw_tokens = len(encoding.encode(text))
    logger.info(
        f"Chunking text: {len(text)} chars, {total_raw_tokens} raw tokens, "
        f"chunk_size={chunk_size}, overlap={chunk_overlap}, encoding={encoding_name}"
    )

    splitter = _build_splitter(chunk_size, chunk_overlap, encoding_name)
    if splitter is not None:
        chunks = splitter.split_text(text)
    else:
        logger.warning("langchain-text-splitters not available, using fallback chunker")
        chunks = _chunk_fallback(text, chunk_size, chunk_overlap, encoding)

    if not chunks:
        logger.warning("Chunking produced zero chunks, returning empty list")
        return [], total_raw_tokens

    chunk_token_counts = []
    for i, chunk in enumerate(chunks):
        ct = len(encoding.encode(chunk))
        chunk_token_counts.append(ct)
        logger.debug(f"  Chunk {i + 1}/{len(chunks)}: {ct} tokens, {len(chunk)} chars")

    total_chunk_tokens = sum(chunk_token_counts)
    avg_tokens = total_chunk_tokens // len(chunks)
    logger.info(
        f"Chunked into {len(chunks)} chunks: "
        f"{total_chunk_tokens} total tokens, "
        f"avg {avg_tokens} tokens/chunk"
    )

    return chunks, total_raw_tokens


def _chunk_fallback(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    encoding: "tiktoken.Encoding",
) -> List[str]:
    """langchain 不可用时的回退方案

    基于 tiktoken 的滑动窗口切割，不做分隔符感知。
    """
    tokens = encoding.encode(text)
    if len(tokens) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    step = chunk_size - chunk_overlap
    if step <= 0:
        step = chunk_size

    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_text = encoding.decode(tokens[start:end])
        if len(chunk_text.strip()) >= 5:
            chunks.append(chunk_text)
        start += step

    return chunks
