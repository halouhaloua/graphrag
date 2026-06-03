from sqlalchemy import Column, String, Text, Integer, Float, Boolean, DateTime, JSON
from app.base_model import BaseModel as AppBaseModel


class ChronicleProject(AppBaseModel):
    __tablename__ = "chronicle_projects"
    title = Column(String(200), nullable=False, comment="志书标题")
    subtitle = Column(String(500), nullable=True, comment="副标题/卷名")
    chronicle_type = Column(
        String(50), nullable=False, default="town", comment="类型: town/county/special"
    )
    region_name = Column(String(200), nullable=True, comment="地区名称")
    scope_description = Column(Text, nullable=True, comment="编纂范围/断限说明")
    editorial_notes = Column(Text, nullable=True, comment="凡例")
    outline_json = Column(JSON, nullable=True, comment="大纲树(JSON)")
    kb_ids = Column(JSON, nullable=True, comment="选定的知识库ID列表")
    file_ids = Column(JSON, nullable=True, comment="选定的文件ID列表")
    status = Column(
        String(20), nullable=False, default="planning", index=True, comment="状态"
    )
    config_json = Column(JSON, nullable=True, comment="写作配置覆盖")
    workflow_run_id = Column(String(100), nullable=True, comment="LangGraph run ID")
    word_count = Column(Integer, default=0, comment="总字数")
    user_id = Column(String(21), nullable=False, index=True, comment="创建者ID")


class ChronicleSection(AppBaseModel):
    __tablename__ = "chronicle_sections"
    project_id = Column(String(21), nullable=False, index=True, comment="所属项目ID")
    parent_id = Column(String(21), nullable=True, index=True, comment="父章节ID")
    title = Column(String(200), nullable=False, comment="章/节/目标题")
    level = Column(Integer, default=1, comment="层级: 1=章 2=节 3=目 4=子目")
    sort_order = Column(Integer, default=0, comment="同级排序")
    content = Column(Text, nullable=True, comment="正文(HTML)")
    status = Column(
        String(20), default="pending", comment="pending/writing/reviewing/approved"
    )
    word_count = Column(Integer, default=0, comment="本节约字数")
    research_data = Column(JSON, nullable=True, comment="该节的研究资料缓存")
    agent_notes = Column(Text, nullable=True, comment="智能体写作备注")


class ChronicleReference(AppBaseModel):
    __tablename__ = "chronicle_references"
    project_id = Column(String(21), nullable=False, index=True, comment="所属项目ID")
    section_id = Column(String(21), nullable=True, index=True, comment="关联章节ID")
    ref_key = Column(String(100), nullable=False, comment="引用标识如ref_001")
    source_type = Column(
        String(50),
        nullable=False,
        comment="kg_file/kb_document/book/periodical/archive/website/other",
    )
    source_id = Column(String(21), nullable=True, comment="来源文件ID")
    source_title = Column(String(500), nullable=True, comment="来源标题")
    author = Column(String(200), nullable=True, comment="作者")
    publisher = Column(String(200), nullable=True, comment="出版者")
    year = Column(String(20), nullable=True, comment="年份")
    volume = Column(String(50), nullable=True, comment="卷期")
    page_info = Column(String(100), nullable=True, comment="页码")
    citation_text = Column(Text, nullable=True, comment="格式化引文")
    quote_text = Column(Text, nullable=True, comment="原文引述")
    confidence = Column(Float, default=1.0, comment="置信度")
    verified = Column(Boolean, default=False, comment="是否已验证")


class ChronicleReview(AppBaseModel):
    __tablename__ = "chronicle_reviews"
    project_id = Column(String(21), nullable=False, index=True, comment="所属项目ID")
    section_id = Column(String(21), nullable=True, index=True, comment="关联章节ID")
    review_type = Column(
        String(30), nullable=False, comment="fact/style/citation/structure/logic"
    )
    reviewer_agent = Column(String(50), nullable=False, comment="审校Agent名称")
    issue = Column(Text, nullable=False, comment="问题描述")
    severity = Column(
        String(20), nullable=False, comment="critical/major/minor/suggestion"
    )
    suggestion = Column(Text, nullable=True, comment="修改建议")
    resolved = Column(Boolean, default=False, comment="是否已解决")
    resolved_at = Column(DateTime, nullable=True, comment="解决时间")


class ChronicleWorkflowLog(AppBaseModel):
    __tablename__ = "chronicle_workflow_logs"
    project_id = Column(String(21), nullable=False, index=True, comment="所属项目ID")
    stage = Column(String(50), nullable=False, comment="节点名称")
    event_type = Column(
        String(50), nullable=False, comment="start/complete/error/interrupt/resume"
    )
    message = Column(Text, nullable=True, comment="日志消息")
    metadata_json = Column(JSON, nullable=True, comment="额外数据")
