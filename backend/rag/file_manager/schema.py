"""
RAG文件管理Schema
"""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


class RagFileManagerResponse(BaseModel):
    """文件管理响应Schema"""
    id: str
    name: str
    file_type: str = Field(alias="fileType")
    parent_id: Optional[str] = Field(None, alias="parentId")
    path: str
    size: int = Field(alias="fileSize")
    file_ext: Optional[str] = Field(None, alias="fileExt")
    mime_type: Optional[str] = Field(None, alias="mimeType")
    storage_path: str = Field(alias="storagePath")
    md5: Optional[str] = None
    scope: str
    has_children: bool = Field(default=False, alias="hasChildren")
    updated_time: Optional[str] = Field(None, alias="updatedTime")
    sys_create_datetime: Optional[datetime] = Field(None, alias="sysCreateDatetime")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class CreateFolderIn(BaseModel):
    """创建文件夹输入"""
    name: str = Field(..., description="文件夹名称")
    parent_id: Optional[str] = Field(None, alias="parentId", description="父文件夹ID")
    scope: str = Field(default='personal', description="作用域: personal/shared")

    model_config = ConfigDict(populate_by_name=True)


class RenameItemIn(BaseModel):
    """重命名输入"""
    name: str = Field(..., description="新名称")


class BatchDeleteIn(BaseModel):
    """批量删除输入"""
    ids: List[str] = Field(..., description="要删除的文件/文件夹ID列表")


class PaginatedResponse(BaseModel):
    """分页响应"""
    items: List[RagFileManagerResponse]
    total: int


class FileUrlResponse(BaseModel):
    """文件URL响应"""
    url: str


class TextContentResponse(BaseModel):
    """文本内容响应"""
    text_content: Optional[str] = Field(None, alias="textContent")
    ocr_status: str = Field(default='none', alias="ocrStatus")
    llm_status: str = Field(default='none', alias="llmStatus")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TextContentUpdate(BaseModel):
    """更新文本内容"""
    text_content: str = Field(..., alias="textContent", description="文本内容")

    model_config = ConfigDict(populate_by_name=True)


class AddToKbIn(BaseModel):
    """添加到知识库输入"""
    kb_id: str = Field(..., alias="kbId", description="目标知识库ID")

    model_config = ConfigDict(populate_by_name=True)
