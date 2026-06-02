from typing import List, Dict, Optional

from pydantic import BaseModel, Field


# ─── 图谱构建 ───
class KnowledgeGraphCreate(BaseModel):
    file_id: str
    graph_data: Optional[dict] = None
    chunks_data: Optional[dict] = None


class ConstructGraphResponse(BaseModel):
    success: bool
    message: str
    graph_data: Optional[Dict] = None


# ─── 提问 ───
class QuestionRequest(BaseModel):
    question: str = Field(..., description="问题")
    file_id: str = Field(..., description="目标文件ID")


class QuestionResponse(BaseModel):
    answer: str
    sub_questions: List[Dict] = []
    retrieved_triples: List[str] = []
    retrieved_chunks: List[str] = []
    reasoning_steps: List[Dict] = []
    visualization_data: Dict = {}


# ─── 三元组管理 ───
class GraphNodeSpec(BaseModel):
    name: str
    category: str = "entity"
    properties: Optional[Dict] = None


class GraphEdgeSpec(BaseModel):
    source: str
    relation: str
    target: str
    source_category: str = "entity"
    target_category: str = "entity"
    source_properties: Optional[Dict] = None
    target_properties: Optional[Dict] = None


class GraphCategoryUpdate(BaseModel):
    node_name: str
    new_category: str


class GraphNodesCreate(BaseModel):
    nodes: List[GraphNodeSpec]


class GraphEdgesCreate(BaseModel):
    edges: List[GraphEdgeSpec]


class GraphEdgeDeleteRequest(BaseModel):
    source: str
    relation: str
    target: str


class GraphEdgeUpdateRequest(BaseModel):
    source: str
    relation: str
    target: str
    new_source: Optional[str] = None
    new_relation: Optional[str] = None
    new_target: Optional[str] = None
    new_source_category: Optional[str] = None
    new_target_category: Optional[str] = None
