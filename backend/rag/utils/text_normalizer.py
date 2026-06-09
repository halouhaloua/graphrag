"""文本规范化工具：实体/关系名称清洗和标准化

功能：
- 全角字母/数字 → 半角
- 中文括号 → 英文括号
- 中文间多余空格移除
- 中文与英文/数字间空格移除
- 外层引号/书名号移除
- 超长名称截断

数据流：
  normalize_entity_name(raw_name) → cleaned_name
"""

import re


def normalize_entity_name(name: str, max_length: int = 100) -> str:
    """规范化实体名称，确保跨 chunk 名称一致。

    Args:
        name (`str`): 原始实体名称
        max_length (`int`, optional): 最大长度，默认 100

    Returns:
        `str`: 规范化后的名称
    """
    if not name or not isinstance(name, str):
        return ""

    # 1. 全角字母 → 半角
    name = name.translate(str.maketrans(
        "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
        "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz",
    ))

    # 2. 全角数字 → 半角
    name = name.translate(str.maketrans("０１２３４５６７８９", "0123456789"))

    # 3. 中文括号 → 英文括号
    name = name.replace("（", "(").replace("）", ")")
    name = name.replace("【", "[").replace("】", "]")

    # 4. 全角波浪线/破折号 → 半角
    name = name.replace("～", "~").replace("—", "-").replace("–", "-")

    # 5. 移除中文之间的空格
    name = re.sub(r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])", r"\1\2", name)

    # 6. 移除中文与英文/数字之间的空格
    name = re.sub(r"([\u4e00-\u9fff])\s+([a-zA-Z0-9])", r"\1\2", name)
    name = re.sub(r"([a-zA-Z0-9])\s+([\u4e00-\u9fff])", r"\1\2", name)

    # 7. 移除首尾空格、引号和书名号
    name = name.strip().strip('\'"\'"“”《》「」『』')

    # 8. 截断超长名称
    if len(name) > max_length:
        name = name[:max_length].rstrip()

    return name
