import { requestClient } from '#/api/request';

/**
 * AI工作流 API
 */

// ============ 类型定义 ============

/** 工作流节点 */
export interface WorkflowDefNode {
  id: string;
  type: string;
  params: Record<string, any>;
  position?: { x: number; y: number };
  error_mode?: string;
}

/** 工作流边 */
export interface WorkflowDefEdge {
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
}

/** 工作流定义 */
export interface WorkflowDef {
  id: string;
  name: string;
  description?: string;
  nodes: WorkflowDefNode[];
  edges: WorkflowDefEdge[];
  global_params?: any;
  is_published: boolean;
  version: number;
  sort: number;
  is_deleted: boolean;
  sys_create_datetime?: string;
  sys_update_datetime?: string;
}

/** 工作流列表响应 */
export interface WorkflowDefListResult {
  items: WorkflowDef[];
  total: number;
}

/** 创建工作流请求 */
export interface WorkflowDefCreateData {
  name: string;
  description?: string;
  nodes?: WorkflowDefNode[];
  edges?: WorkflowDefEdge[];
}

// ============ API 函数 ============

/** 获取工作流定义列表 */
export async function getWorkflowDefListApi(params?: {
  page?: number;
  pageSize?: number;
  name?: string;
}) {
  return requestClient.get<WorkflowDefListResult>(
    '/api/ai-workflow/defs',
    { params },
  );
}

/** 获取工作流定义详情 */
export async function getWorkflowDefDetailApi(id: string) {
  return requestClient.get<WorkflowDef>(`/api/ai-workflow/defs/${id}`);
}

/** 创建工作流定义 */
export async function createWorkflowDefApi(data: WorkflowDefCreateData) {
  return requestClient.post<WorkflowDef>('/api/ai-workflow/defs', data);
}

/** 更新工作流定义 */
export async function updateWorkflowDefApi(
  id: string,
  data: Partial<WorkflowDefCreateData>,
) {
  return requestClient.put<WorkflowDef>(`/api/ai-workflow/defs/${id}`, data);
}

/** 删除工作流定义 */
export async function deleteWorkflowDefApi(id: string) {
  return requestClient.delete(`/api/ai-workflow/defs/${id}`);
}

/** 发布/取消发布工作流 */
export async function publishWorkflowDefApi(id: string, publish = true) {
  return requestClient.post(
    `/api/ai-workflow/defs/${id}/publish?publish=${publish}`,
  );
}

/** 执行工作流（异步） */
export async function runWorkflowApi(
  id: string,
  inputParams?: Record<string, any>,
) {
  return requestClient.post(`/api/ai-workflow/defs/${id}/run`, {
    input_params: inputParams,
  });
}

/** 获取节点类型列表 */
export async function getNodeTypesApi() {
  return requestClient.get<any[]>('/api/ai-workflow/nodes');
}

// ============ 实例相关 ============

/** 工作流实例 */
export interface WorkflowInstance {
  id: string;
  workflow_def_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  input_params?: any;
  output_result?: any;
  error?: string;
  started_at?: string;
  finished_at?: string;
  sys_create_datetime?: string;
}

/** 节点执行日志 */
export interface WorkflowNodeLog {
  id: string;
  instance_id: string;
  node_id: string;
  node_type: string;
  status: string;
  input_data?: any;
  output_data?: any;
  error?: string;
  started_at?: string;
  finished_at?: string;
  duration_ms?: number;
}

/** 获取实例列表 */
export async function getWorkflowInstancesApi(params?: {
  page?: number;
  pageSize?: number;
  status?: string;
  defId?: string;
}) {
  return requestClient.get<{ items: WorkflowInstance[]; total: number }>(
    '/api/ai-workflow/instances',
    { params },
  );
}

/** 获取实例详情 */
export async function getWorkflowInstanceApi(id: string) {
  return requestClient.get<WorkflowInstance>(`/api/ai-workflow/instances/${id}`);
}

/** 获取节点执行日志 */
export async function getWorkflowNodeLogsApi(instId: string) {
  return requestClient.get<WorkflowNodeLog[]>(
    `/api/ai-workflow/instances/${instId}/logs`,
  );
}

/** 取消执行 */
export async function cancelWorkflowApi(instId: string) {
  return requestClient.post(`/api/ai-workflow/instances/${instId}/cancel`);
}

// ============ 团队相关 ============

/** 团队角色定义（匹配后端 TeamRoleSchema） */
export interface TeamRoleDef {
  agent_description?: string;
  model_name?: string;
  max_iterations?: number;
  tools: string[];
  termination_conditions?: any[];
}

/** 团队配置 */
export interface TeamConfig {
  id: string;
  name: string;
  description?: string;
  team_rules: string;
  start_role: string;
  roles: Record<string, TeamRoleDef>;
  yaml_source?: string;
  is_active: boolean;
  sys_create_datetime?: string;
}

/** 获取团队列表 */
export async function getTeamListApi(params?: {
  page?: number;
  pageSize?: number;
  name?: string;
}) {
  return requestClient.get<{ items: TeamConfig[]; total: number }>(
    '/api/ai-workflow/teams',
    { params },
  );
}

/** 获取团队详情 */
export async function getTeamDetailApi(id: string) {
  return requestClient.get<TeamConfig>(`/api/ai-workflow/teams/${id}`);
}

/** 创建团队 */
export async function createTeamApi(data: {
  name: string;
  description?: string;
  team_rules: string;
  start_role: string;
  roles: Record<string, TeamRoleDef>;
}) {
  return requestClient.post<TeamConfig>('/api/ai-workflow/teams', data);
}

/** 更新团队 */
export async function updateTeamApi(
  id: string,
  data: Partial<{
    name: string;
    description: string;
    team_rules: string;
    start_role: string;
    roles: Record<string, TeamRoleDef>;
    is_active: boolean;
  }>,
) {
  return requestClient.put<TeamConfig>(`/api/ai-workflow/teams/${id}`, data);
}

/** 删除团队 */
export async function deleteTeamApi(id: string) {
  return requestClient.delete(`/api/ai-workflow/teams/${id}`);
}

/** 从YAML导入团队 */
export async function importTeamYamlApi(data: {
  yaml_content: string;
  name?: string;
  description?: string;
}) {
  return requestClient.post<TeamConfig>('/api/ai-workflow/teams/import', data);
}

/** 运行团队 */
export async function runTeamApi(id: string, inputParams?: Record<string, any>) {
  return requestClient.post(`/api/ai-workflow/teams/${id}/run`, {
    input_params: inputParams,
  });
}
