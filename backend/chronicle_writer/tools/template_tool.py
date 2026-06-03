import importlib
import json
from agentscope.tool import FunctionTool


def load_chronicle_template(chronicle_type: str) -> str:
    """加载志书篇目模板。

    Args:
        chronicle_type: 志书类型: "town"(镇志) / "county"(县志) / "special"(专志)

    Returns:
        包含 name/outline_template/editorial_notes_template 的字典JSON
    """
    try:
        module = importlib.import_module(
            f"chronicle_writer.templates.{chronicle_type}_zhi"
        )
        return json.dumps(module.TEMPLATE, ensure_ascii=False)
    except ImportError:
        return json.dumps(
            {"error": f"未知的志书类型: {chronicle_type}"}, ensure_ascii=False
        )


def list_available_templates() -> str:
    """列出所有可用的志书模板。

    Returns:
        模板列表JSON
    """
    templates = [
        {"type": "town", "name": "镇志", "description": "镇级地方志标准篇目"},
        {"type": "county", "name": "县志", "description": "县级地方志标准篇目"},
        {"type": "special", "name": "专志", "description": "部门志/行业志标准篇目"},
    ]
    return json.dumps(templates, ensure_ascii=False)


template_tool = FunctionTool(
    func=load_chronicle_template,
    name="LoadTemplate",
    description="加载志书篇目模板，返回完整篇目结构",
    is_read_only=True,
)

list_templates_tool = FunctionTool(
    func=list_available_templates,
    name="ListTemplates",
    description="列出所有可用的志书模板类型",
    is_read_only=True,
)
