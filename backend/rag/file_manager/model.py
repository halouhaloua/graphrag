"""
RAG文件管理模型
"""
from sqlalchemy import Column, String, Text, BigInteger, Integer, Index

from app.base_model import BaseModel


class RagFileManager(BaseModel):
    """RAG文件管理模型"""
    __tablename__ = "rag_file_manager"

    name = Column(String(255), nullable=False, comment="文件/文件夹名称")
    file_type = Column(String(10), default='file', comment="类型: file/folder")
    parent_id = Column(String(21), nullable=True, comment="父文件夹ID")
    path = Column(Text, nullable=False, default='', comment="文件路径")
    size = Column(BigInteger, default=0, comment="文件大小(字节)")
    file_ext = Column(String(50), nullable=True, comment="文件扩展名")
    mime_type = Column(String(200), nullable=True, comment="MIME类型")
    storage_path = Column(Text, nullable=False, default='', comment="存储路径")
    md5 = Column(String(32), nullable=True, comment="文件MD5")
    scope = Column(String(20), default='personal', comment="作用域: personal/shared")
    text_content = Column(Text, nullable=True, comment="提取/OCR/编辑后的文本内容")
    ocr_status = Column(String(20), default='none', comment="OCR状态: none/pending/completed/failed")
    llm_status = Column(String(20), default='none', comment="多模态大模型识别状态: none/pending/completed/failed")

    __table_args__ = (
        Index('ix_rag_file_parent_type', 'parent_id', 'file_type'),
        Index('ix_rag_file_scope', 'scope'),
    )
