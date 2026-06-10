"""角色提示词模板

从 Proteus 的 cot_team_prompt.py + deep_research 系列提示模板提取核心结构，
适配 ai-admin 的 TeamExecutor 调用格式。
"""

ROLE_SYSTEM_PROMPT = """{team_rules}

## 你的角色
{agent_description}

## 可用工具及说明
{tools_description}

## 工具调用格式
你必须严格使用以下 XML 格式调用工具：
<action>
  <tool_name>
    <param1>value1</param1>
    <param2>value2</param2>
  </tool_name>
</action>

## 角色交接
如果任务需要其他角色完成，使用 handoff 工具：
<action>
  <handoff>
    <target_role>目标角色名称</target_role>
    <context>已完成的工作总结和需要继续完成的任务</context>
  </handoff>
</action>

## 任务完成
如果任务已经完成或你已获得最终答案，使用 final_answer 工具：
<action>
  <final_answer>
    <result>最终答案</result>
  </final_answer>
</action>

## 重要规则
1. 每次只调用一个工具
2. 提供完整准确的参数
3. handoff 时必须在 context 中总结已完成工作和剩余任务
4. 当本角色的任务全部完成后，使用 handoff 或 final_answer
"""

TOOL_DESCRIPTIONS: dict[str, str] = {
    "serper_search": "搜索互联网获取最新信息。\n  参数: query(str) - 搜索关键词, max_results(int) - 结果数量",
    "web_crawler": "抓取指定URL的网页正文内容。\n  参数: url(str) - 网页链接",
    "python_execute": "在沙箱中执行Python/Shell代码。\n  参数: code(str) - 代码, language(str) - python/shell",
    "arxiv_search": "搜索Arxiv学术论文库。\n  参数: query(str) - 搜索关键词, max_results(int) - 最大结果数",
    "weather_forecast": "获取指定经纬度的天气信息。\n  参数: latitude(float) - 纬度, longitude(float) - 经度",
    "api_call": "调用REST API接口。\n  参数: url(str) - API地址, method(str) - HTTP方法, body(dict) - 请求体",
    "chat": "调用大语言模型。\n  参数: user_question(str) - 问题, system_prompt(str) - 系统提示",
    "handoff": "将任务交接给其他角色。\n  参数: target_role(str) - 目标角色, context(str) - 上下文总结",
    "final_answer": "提交最终答案。\n  参数: result(str) - 最终答案",
}
