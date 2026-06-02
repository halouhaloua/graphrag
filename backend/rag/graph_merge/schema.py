from typing import List, Dict, Optional

from pydantic import BaseModel, Field


class GraphMergeRequest(BaseModel):
    old_graph_data: List[Dict] = Field(
        ..., description="旧文本的图谱 JSON 数据（不含 community）"
    )
    new_graph_data: List[Dict] = Field(
        ..., description="新文本的图谱 JSON 数据（不含 community）"
    )
    struct_weight: float = Field(
        default=0.3, ge=0, le=1, description="结构相似度权重"
    )
    max_total_communities: Optional[int] = Field(
        default=None, description="最大社区数量"
    )


class GraphMergeResponse(BaseModel):
    success: bool
    message: str
    merged_graph_data: Optional[List[Dict]] = None
    community_count: Optional[int] = None
    total_nodes: Optional[int] = None
    total_edges: Optional[int] = None


class KbMergeResponse(BaseModel):
    success: bool
    message: str
    virtual_file_id: Optional[str] = None
    community_count: Optional[int] = None
    total_nodes: Optional[int] = None
    total_edges: Optional[int] = None
    file_count: Optional[int] = None


class IncrementalUpdateResponse(BaseModel):
    success: bool
    message: str
    community_count: Optional[int] = None
    total_nodes: Optional[int] = None
    total_edges: Optional[int] = None
