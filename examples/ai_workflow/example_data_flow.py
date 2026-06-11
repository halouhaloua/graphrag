"""
WorkflowEngine 节点间数据传递示例

使用方法:
    cd backend && python ../examples/ai_workflow/example_data_flow.py

场景:
    1. 线性链: _start → search_1 → llm_1 → _end
    2. 并行执行: _start → [search_web, search_news] → llm_summary → _end
    3. 错误传播: 上游节点失败,下游被取消
"""

import json
import re
import textwrap
from typing import Any

# ── 变量引用解析（与 WorkflowEngine.resolve_params 逻辑完全一致） ──────────

_REF_PATTERN = re.compile(r"\$\{(\w+)\.(\w+)\}")


def resolve_params(params: dict, node_outputs: dict[str, dict]) -> dict:
    """解析节点参数中的变量引用

    将参数中 ``\\${nodeId.key}`` 替换为上游节点的输出值。
    """

    def _resolve(value: Any) -> Any:
        if isinstance(value, str):

            def _replacer(m: re.Match) -> str:
                nid, key = m.group(1), m.group(2)
                out = node_outputs.get(nid, {})
                return str(out.get(key, m.group(0)))

            return _REF_PATTERN.sub(_replacer, value)
        if isinstance(value, dict):
            return {k: _resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_resolve(v) for v in value]
        return value

    return {k: _resolve(v) for k, v in params.items()}


# ── 辅助函数 ──────────────────────────────────────────────────────────


def print_title(title: str):
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def print_step(label: str, content: str = "", indent: int = 2):
    prefix = " " * indent
    print(f"{prefix}-> {label}")
    if content:
        for line in content.strip().split("\n"):
            print(f"{prefix}  {line}")


def print_dict(data: dict, indent: int = 4) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def simulate_execute(node_id: str, params: dict, node_outputs: dict) -> dict:
    """模拟节点执行：解析参数 → 打印 → 返回模拟输出"""
    resolved = resolve_params(params, node_outputs)
    print(f"\n    ┌─ {node_id}")
    print(f"    │  原始参数: {json.dumps(params, ensure_ascii=False)}")
    print(f"    │  解析参数: {json.dumps(resolved, ensure_ascii=False)}")
    return resolved


# ══════════════════════════════════════════════════════════════════════
# 场景 1: 线性链
# ══════════════════════════════════════════════════════════════════════

print_title("场景 1: 线性链 — 搜索 → LLM 总结")
print("工作流: _start → search_1 → llm_1 → _end")
print()

# node_outputs 是引擎内部的共享累加器
# 每执行完一个节点，输出被写入其中
node_outputs: dict[str, dict] = {}

# ── 第 0 层: _start ──
print_step("第 0 层: [_start] 无入边，最先执行")
start_out = {"result": "start", "success": True}
node_outputs["start_1"] = start_out
print(f"          输出 → node_outputs['start_1'] = {start_out}")

# ── 第 1 层: search_1 ──
print_step("第 1 层: [search_1] 执行搜索")
resolved = simulate_execute("search_1", {"query": "2024 AI trends"}, node_outputs)
search_out = {
    "result": "AI trends in 2024: multimodal models, "
    "edge AI, autonomous agents, and AI governance",
    "count": 10,
    "success": True,
}
node_outputs["search_1"] = search_out
print(f"    │  输出 → node_outputs['search_1'] = {json.dumps(search_out, ensure_ascii=False)}")

# ── 第 2 层: llm_1 ──
print_step(
    "第 2 层: [llm_1] LLM 对话 — 引用 search_1 的结果",
    "用户在前端参数面板中填入:\n"
    '  user_question = "请总结: ${search_1.result}\\n\\n用中文回答"',
)
resolved = simulate_execute(
    "llm_1",
    {
        "system_prompt": "你是一个AI助手",
        "user_question": "请总结以下搜索结果:\n${search_1.result}\n\n用中文回答",
        "temperature": 0.7,
    },
    node_outputs,
)
print("    │")
print(f"    │  ^^ 注意 ${'search_1.result'} 已被替换为搜索节点的实际返回内容")

llm_out = {
    "result": "2024年AI趋势主要包括多模态模型、"
    "边缘AI、自主智能体和AI治理四大方向。",
    "success": True,
}
node_outputs["llm_1"] = llm_out
print(f"    │  输出 → node_outputs['llm_1'] = {json.dumps(llm_out, ensure_ascii=False)}")

# ── 第 3 层: _end ──
print_step("第 3 层: [_end] 收尾")
node_outputs["end_1"] = {"result": "end", "success": True}

# ── 最终输出 ──
print()
print_step("最终 node_outputs (所有节点输出的聚合)", indent=0)
print(textwrap.indent(print_dict(node_outputs), "     "))

print()
print_step("引擎写入 instance.output_result (只保留 .result)", indent=0)
final = {k: v.get("result", v) for k, v in node_outputs.items()}
print(textwrap.indent(print_dict(final), "     "))


# ══════════════════════════════════════════════════════════════════════
# 场景 2: 并行执行
# ══════════════════════════════════════════════════════════════════════

print_title("场景 2: 并行执行 — 两个搜索同时进行，LLM 汇总")
print("工作流: _start → [search_web, search_news] → llm_summary → _end")
print()

node_outputs = {"start_1": {"result": "start", "success": True}}

# ── 第 1 层: search_web, search_news（并行）──
print_step(
    "第 1 层: [search_web, search_news] 并行执行",
    "同层节点通过 asyncio.gather 并发执行，\n"
    "每个节点有独立 DB session，互不干扰。",
)

resolved = simulate_execute("search_web", {"query": "AI in healthcare"}, node_outputs)
search_web_out = {
    "result": "AI in healthcare: diagnostic imaging, "
    "drug discovery, personalized medicine",
    "count": 8,
    "success": True,
}
node_outputs["search_web"] = search_web_out
print(f"    │  输出: {json.dumps(search_web_out, ensure_ascii=False)}")

resolved = simulate_execute("search_news", {"query": "AI latest news"}, node_outputs)
search_news_out = {
    "result": "Today AI news: new LLM released, "
    "AI regulation debate continues",
    "count": 15,
    "success": True,
}
node_outputs["search_news"] = search_news_out
print(f"    │  输出: {json.dumps(search_news_out, ensure_ascii=False)}")

# ── 第 2 层: llm_summary（引用两个上游）──
print_step(
    "第 2 层: [llm_summary] 汇总两个搜索结果",
    "用户同时引用了两个不同节点的输出:",
)
resolved = simulate_execute(
    "llm_summary",
    {
        "user_question": (
            "综合以下信息:\n"
            "- 网页: ${search_web.result}\n"
            "- 新闻: ${search_news.result}\n\n"
            "请给出总结"
        )
    },
    node_outputs,
)
print("    │")
print("    │  ^^ 两个 ${{...}} 同时被替换")
print(f"    │  search_web.result → '{search_web_out['result'][:30]}...'")
print(f"    │  search_news.result → '{search_news_out['result'][:30]}...'")

llm_summary_out = {
    "result": "AI在医疗领域的应用集中在影像诊断和药物研发，"
    "同时最新AI新闻显示大模型竞争加剧，监管讨论升温。",
    "success": True,
}
node_outputs["llm_summary"] = llm_summary_out
node_outputs["end_1"] = {"result": "end", "success": True}

print()
print_step("最终 node_outputs", indent=0)
print(textwrap.indent(print_dict(node_outputs), "     "))

# ── 展示限制: 同层节点不能互引用 ──
print()
print_step(
    "⚠ 关键限制: 同层节点不能互相引用",
    "如果 search_news 想引用 search_web 的结果来优化搜索词：\n"
    "例如 params = {'query': '结合 ${search_web.result} 进一步搜索'}\n"
    "但在第 1 层执行 search_news 时，search_web 尚未完成，\n"
    "node_outputs 中还没有 search_web 的条目，引用保持原样。",
)
early_outputs = {"start_1": {"result": "start"}}
cross_resolved = resolve_params(
    {"query": "${search_web.result} 相关的最新进展"}, early_outputs
)
print(f"    结果: '{cross_resolved['query']}'")
print(f"    ↑ ${'search_web.result'} 未被替换（节点还不存在）")


# ══════════════════════════════════════════════════════════════════════
# 场景 3: 错误传播
# ══════════════════════════════════════════════════════════════════════

print_title("场景 3: 错误传播 — 上游失败，下游被取消")
print("工作流: _start → search_1 → llm_1(write_code) → llm_2(review) → _end")
print("                                      ↑ error_mode=stop")
print()

node_outputs = {"start_1": {"result": "start", "success": True}}

# ── 第 1 层: search_1（成功）──
print_step("第 1 层: [search_1] 执行成功")
resolved = simulate_execute("search_1", {"query": "Python async patterns"}, node_outputs)
search_out = {"result": "asyncio, await, gather, TaskGroup patterns...", "success": True}
node_outputs["search_1"] = search_out
print(f"    │  输出: {json.dumps(search_out, ensure_ascii=False)}")

# ── 第 2 层: llm_1（失败！）──
print_step(
    "第 2 层: [llm_1(write_code)] 执行失败",
    "假设这个节点调用 LLM 写代码，但 API 返回了 500 错误。"
)
resolved = simulate_execute(
    "llm_1",
    {
        "system_prompt": "你是一个Python专家",
        "user_question": "基于 ${search_1.result} 写一个异步爬虫",
    },
    node_outputs,
)
print("    │")
print("    │  ❌ LLM API 返回 500 错误!")
print("    │  error_mode = 'stop'（默认），引擎标记整个工作流失败")

# 引擎的行为:
# 1. llm_1 的 execute() 抛异常或返回 {"error": "..."}
# 2. error_mode == "stop" → cancel = True
# 3. 后续所有节点被记录为 cancelled
# 4. instance.status = "failed"

cancel = True  # llm_1 失败，引擎设置 cancel 标志
llm_1_error = "LLM API returned 500: Internal Server Error"
node_outputs["llm_1"] = {"error": llm_1_error, "success": False}
print("    │  node_outputs['llm_1'] = {json.dumps(node_outputs['llm_1'], ensure_ascii=False)}")
print("    │  cancel = True")

# ── 第 3 层: llm_2（已被取消）──
print_step(
    "第 3 层: [llm_2(review)] 被取消",
    "因为 cancel 为 True，引擎跳过这一层的所有节点，\n"
    "只在数据库中将它们记录为 cancelled 状态。"
)
if cancel:
    print("    │  ❌ 跳过 llm_2，标记为 cancelled")
    node_outputs["llm_2"] = {"status": "cancelled", "error": "前置节点失败"}

# ── 第 4 层: _end ──
if cancel:
    print_step("第 4 层: [_end] 也被取消")
    node_outputs["end_1"] = {"status": "cancelled", "error": "前置节点失败"}

print()
print_step("最终 node_outputs", indent=0)
print(textwrap.indent(print_dict(node_outputs), "     "))

print()
print_step("instance 状态", indent=0)
print(
    textwrap.indent(
        print_dict(
            {
                "status": "failed",
                "error": f"节点 llm_1 执行失败: {llm_1_error}",
                "output_result": {
                    k: v.get("result", v)
                    for k, v in node_outputs.items()
                    if "result" in v
                },
            }
        ),
        "     ",
    )
)


# ══════════════════════════════════════════════════════════════════════
print()
print("✅ 三个场景演示完毕")
print()
print("核心要点:")
print("  1. 节点输出写入共享 node_outputs 字典，按 node_id 索引")
print("  2. 下游通过 ${nodeId.key} 语法引用上游输出")
print("  3. resolve_params() 在节点执行前做替换，替换后的参数传给 execute()")
print("  4. 同层节点可并行执行，但不可互相引用（互不依赖是并行的前提）")
print("  5. error_mode=stop 时，失败节点的后续节点全部取消")
print("  6. 最终 output_result 聚合所有节点的 .result 字段")
