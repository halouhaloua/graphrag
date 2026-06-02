from sqlalchemy import Column, String, Text, Boolean, Integer, JSON, ForeignKey, UniqueConstraint

from app.base_model import BaseModel


class KnowledgeBase(BaseModel):
    __tablename__ = "rag_knowledge_base"

    name = Column(String(200), unique=True, nullable=False, comment="知识库名称")
    description = Column(Text, nullable=True, comment="描述")
    kb_type = Column(String(20), default="user", comment="类型: user/demo")


class KnowledgeBaseFile(BaseModel):
    __tablename__ = "rag_knowledge_base_file"

    kb_id = Column(
        String(21),
        ForeignKey("rag_knowledge_base.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属知识库",
    )
    filename = Column(String(255), nullable=False, comment="文件名")
    content = Column(Text, nullable=False, comment="文本内容")
    file_type = Column(String(20), nullable=True, comment="文件类型")
    file_size = Column(Integer, default=0, comment="文件大小(字节)")
    schema_json = Column(JSON, nullable=True, comment="该文件的自定义Schema定义")
    has_graph = Column(Boolean, default=False, comment="是否已构建图谱")


class KnowledgeBaseRole(BaseModel):
    __tablename__ = "rag_knowledge_base_role"

    role_id = Column(
        String(21),
        ForeignKey("core_role.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="角色ID",
    )
    kb_id = Column(
        String(21),
        ForeignKey("rag_knowledge_base.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="知识库ID",
    )

    __table_args__ = (
        UniqueConstraint("role_id", "kb_id", name="uq_role_kb"),
    )
