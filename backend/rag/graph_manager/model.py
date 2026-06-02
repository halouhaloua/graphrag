from sqlalchemy import Column, String, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func

from app.base_model import BaseModel


class KnowledgeGraph(BaseModel):
    __tablename__ = "rag_knowledge_graph"

    file_id = Column(
        String(21),
        ForeignKey("rag_knowledge_base_file.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        comment="所属文件",
    )
    graph_data = Column(JSON, nullable=True, comment="图谱结构数据(节点+边)")
    chunks_data = Column(JSON, nullable=True, comment="文本块数据 {chunk_id: text}")
    built_at = Column(DateTime, server_default=func.now(), comment="构建时间")
