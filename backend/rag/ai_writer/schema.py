from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ─── Conversation ───

class WriterConversationCreate(BaseModel):
    title: Optional[str] = "新对话"
    model_name: Optional[str] = "qwen"


class WriterConversationUpdate(BaseModel):
    title: Optional[str] = None


class WriterConversationResponse(BaseModel):
    id: str
    title: str
    user_id: str
    model_name: Optional[str]
    sys_create_datetime: datetime
    sys_update_datetime: datetime

    class Config:
        from_attributes = True


class WriterConversationListResponse(BaseModel):
    items: List[WriterConversationResponse]
    total: int


# ─── Message ───

class WriterMessageCreate(BaseModel):
    conversation_id: str
    role: str
    content: str
    model_name: Optional[str] = None


class WriterMessageUpdate(BaseModel):
    content: str


class WriterMessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    model_name: Optional[str]
    sys_create_datetime: datetime

    class Config:
        from_attributes = True


class WriterMessageListResponse(BaseModel):
    items: List[WriterMessageResponse]
    total: int


# ─── Document ───

class WriterDocumentCreate(BaseModel):
    title: Optional[str] = "未命名文档"
    content: str


class WriterDocumentUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


class WriterDocumentResponse(BaseModel):
    id: str
    conversation_id: str
    message_id: str
    title: str
    content: str
    sys_create_datetime: datetime
    sys_update_datetime: datetime

    class Config:
        from_attributes = True


class WriterDocumentListResponse(BaseModel):
    items: List[WriterDocumentResponse]
    total: int


# ─── Chat ───

class WriterChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    question: str = Field(..., description="用户问题")
    history: Optional[List[dict]] = Field(default=None, description="历史消息 [{role, content}]")


class WriterEditRequest(BaseModel):
    content: str = Field(..., description="要处理的文本内容")
    instruction: str = Field(default="polish", description="处理方式: polish / rewrite / custom")
    custom_prompt: Optional[str] = Field(default=None, description="自定义指令（instruction=custom 时必填）")


class WriterMessageEditRequest(BaseModel):
    content: str = Field(..., description="要处理的消息文本内容")
    instruction: str = Field(default="polish", description="处理方式: polish / rewrite / custom")
    custom_prompt: Optional[str] = Field(default=None, description="自定义指令（instruction=custom 时必填）")
