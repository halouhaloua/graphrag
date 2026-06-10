import { requestClient } from '#/api/request';
import { streamRequestClient } from '#/api/stream-request';

// ─── Types ───
export interface KnowledgeBase {
  id: string;
  name: string;
  description?: string;
  kb_type: string;
  is_public: boolean;
  file_count: number;
  sys_create_datetime: string;
  sys_update_datetime: string;
}

export interface KnowledgeBaseListResult {
  items: KnowledgeBase[];
  total: number;
}

export interface KnowledgeBaseFile {
  id: string;
  kb_id: string;
  filename: string;
  file_type?: string;
  file_size: number;
  has_graph: boolean;
  schema_json?: Record<string, any>;
  sys_create_datetime: string;
}

export interface KnowledgeBaseFileListResult {
  items: KnowledgeBaseFile[];
  total: number;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
  categories: GraphCategory[];
  stats: GraphStats;
}

export interface GraphNode {
  id: string;
  name: string;
  category: string;
  symbolSize?: number;
  properties?: Record<string, any>;
}

export interface GraphLink {
  source: string;
  target: string;
  name: string;
  value?: number;
}

export interface GraphCategory {
  name: string;
  itemStyle?: Record<string, any>;
}

export interface GraphStats {
  total_nodes: number;
  total_edges: number;
  displayed_nodes?: number;
  displayed_edges?: number;
}

export interface IRCoTConfig {
  enable_ircot: boolean;
  max_steps: number;
}

export interface ChatConversation {
  id: string;
  title: string;
  user_id: string;
  model_name?: string;
  sys_create_datetime: string;
  sys_update_datetime: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  model_name?: string;
  sys_create_datetime: string;
}

export interface QuestionResult {
  answer: string;
  sub_questions: any[];
  retrieved_triples: string[];
  retrieved_chunks: string[];
  reasoning_steps: any[];
  visualization_data: Record<string, any>;
}

// ─── Knowledge Base CRUD ───
export async function getKnowledgeBaseListApi(params?: {
  page?: number;
  pageSize?: number;
  name?: string;
}) {
  return requestClient.get<KnowledgeBaseListResult>(
    '/rag/api/knowledge-bases',
    { params },
  );
}

export async function getKnowledgeBaseDetailApi(kbId: string) {
  return requestClient.get<KnowledgeBase>(
    `/rag/api/knowledge-base/${kbId}`,
  );
}

export async function createKnowledgeBaseApi(data: {
  name: string;
  description?: string;
  is_public?: boolean;
  permissions?: {
    role_ids?: string[];
    dept_ids?: string[];
    user_ids?: string[];
  };
}) {
  return requestClient.post<KnowledgeBase>('/rag/api/knowledge-base', data);
}

export async function updateKnowledgeBaseApi(
  kbId: string,
  data: {
    name?: string;
    description?: string;
    is_public?: boolean;
    permissions?: {
      role_ids?: string[];
      dept_ids?: string[];
      user_ids?: string[];
    };
  },
) {
  return requestClient.put<KnowledgeBase>(
    `/rag/api/knowledge-base/${kbId}`,
    data,
  );
}

export async function deleteKnowledgeBaseApi(kbId: string) {
  return requestClient.delete(`/rag/api/knowledge-base/${kbId}`);
}

// ─── File Management ───
export async function uploadFilesApi(
  kbId: string,
  files: File[],
  schemaFile?: File | null,
) {
  const formData = new FormData();
  files.forEach((f) => formData.append('files', f));
  if (schemaFile) {
    formData.append('schema_file', schemaFile);
  }
  return requestClient.post(
    `/rag/api/knowledge-base/${kbId}/files/upload`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
}

export async function getFileListApi(kbId: string) {
  return requestClient.get<KnowledgeBaseFileListResult>(
    `/rag/api/knowledge-base/${kbId}/files`,
  );
}

export async function getFileDetailApi(kbId: string, fileId: string) {
  return requestClient.get<KnowledgeBaseFile>(
    `/rag/api/knowledge-base/${kbId}/files/${fileId}`,
  );
}

export async function deleteFileApi(kbId: string, fileId: string) {
  return requestClient.delete(
    `/rag/api/knowledge-base/${kbId}/files/${fileId}`,
  );
}

export async function updateFileSchemaApi(
  kbId: string,
  fileId: string,
  schema: Record<string, any>,
) {
  return requestClient.put(
    `/rag/api/knowledge-base/${kbId}/files/${fileId}/schema`,
    { schema },
  );
}

// ─── Graph Operations ───
export async function constructGraphApi(
  kbId: string,
  fileId: string,
  clientId?: string,
) {
  const params: Record<string, any> = {};
  if (clientId) params.client_id = clientId;
  return requestClient.post(
    `/rag/api/knowledge-base/${kbId}/files/${fileId}/construct-graph`,
    {},
    { params },
  );
}

export async function getGraphDataApi(
  kbId: string,
  fileId: string,
  maxNodes?: number,
) {
  const params: Record<string, any> = {};
  if (maxNodes !== undefined) params.maxNodes = maxNodes;
  return requestClient.get<GraphData>(
    `/rag/api/knowledge-base/${kbId}/files/${fileId}/graph`,
    { params },
  );
}

export async function getKbMergedGraphApi(kbId: string) {
  return requestClient.get<GraphData>(
    `/rag/api/knowledge-base/${kbId}/merged-graph`,
  );
}

export async function mergeKbGraphsApi(kbId: string) {
  return requestClient.post(`/rag/api/knowledge-base/${kbId}/merge-graphs`);
}

export async function incrementalFileUpdateApi(
  kbId: string,
  fileId: string,
  file: File,
) {
  const formData = new FormData();
  formData.append('file', file);
  return requestClient.post(
    `/rag/api/knowledge-base/${kbId}/files/${fileId}/incremental-update`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
}

export async function getKbMergedGraphStatusApi(kbId: string) {
  return requestClient.get<{
    exists: boolean;
    file_count: number;
    total_nodes: number;
    total_edges: number;
    built_at: string | null;
  }>(`/rag/api/knowledge-base/${kbId}/merged-graph/status`);
}

export interface PaginatedGraphItems<T> {
  items: T[];
  total: number;
}

export async function getGraphNodesApi(
  kbId: string,
  fileId: string,
  page: number,
  pageSize: number,
) {
  return requestClient.get<PaginatedGraphItems<GraphNode>>(
    `/rag/api/knowledge-base/${kbId}/files/${fileId}/graph/nodes`,
    { params: { page, pageSize } },
  );
}

export async function getGraphEdgesApi(
  kbId: string,
  fileId: string,
  page: number,
  pageSize: number,
) {
  return requestClient.get<PaginatedGraphItems<GraphLink>>(
    `/rag/api/knowledge-base/${kbId}/files/${fileId}/graph/edges`,
    { params: { page, pageSize } },
  );
}

export async function reconstructGraphApi(
  kbId: string,
  fileId: string,
  clientId?: string,
) {
  const params: Record<string, any> = {};
  if (clientId) params.client_id = clientId;
  return requestClient.post(
    `/rag/api/knowledge-base/${kbId}/files/${fileId}/reconstruct`,
    {},
    { params },
  );
}

// ─── SSE 流式事件助手 ───

const STREAM_EVENT_TYPES = new Set([
  'token', 'metadata', 'reasoning_steps', 'visualization',
  'done', 'status', 'error', 'answer_start', 'answer_end',
  'reasoning_start', 'reasoning_end', 'ircot_start', 'ircot_end', 'answer_found',
]);

interface StreamAccumulator {
  answerParts: string[];
  subQuestions: any[];
  triples: string[];
  chunks: string[];
  reasoningSteps: any[];
  visualizationData: Record<string, any>;
}

interface StreamCallbacks {
  onToken?: (token: string) => void;
  onReasoningToken?: (token: string) => void;
  onMetadata?: (data: any) => void;
  onReasoningSteps?: (data: any) => void;
  onVisualization?: (data: any) => void;
  onDone?: (data: any) => void;
  onStatus?: (progress: number, message: string) => void;
  onError?: (error: Error) => void;
  onComplete?: () => void;
}

function createStreamAccumulator(): StreamAccumulator {
  return { answerParts: [], subQuestions: [], triples: [], chunks: [], reasoningSteps: [], visualizationData: {} };
}

function handleStreamEvent(
  data: any,
  acc: StreamAccumulator,
  callbacks: StreamCallbacks | undefined,
): Promise<QuestionResult> | null {
  if (!STREAM_EVENT_TYPES.has(data.type)) return null;

  switch (data.type) {
    case 'token':
      if (data.phase === 'reasoning') {
        callbacks?.onReasoningToken?.(data.text);
      } else {
        acc.answerParts.push(data.text);
        callbacks?.onToken?.(data.text);
      }
      break;
    case 'metadata':
      acc.subQuestions = data.sub_questions || [];
      acc.triples = data.triples || [];
      acc.chunks = data.chunks || [];
      callbacks?.onMetadata?.(data);
      break;
    case 'reasoning_steps':
      acc.reasoningSteps = data.data?.reasoning_steps || [];
      callbacks?.onReasoningSteps?.(data.data);
      break;
    case 'visualization':
      acc.visualizationData = data.data || {};
      callbacks?.onVisualization?.(data.data);
      break;
    case 'done':
      callbacks?.onDone?.(data);
      return Promise.resolve({
        answer: data.answer || acc.answerParts.join(''),
        sub_questions: acc.subQuestions,
        retrieved_triples: acc.triples,
        retrieved_chunks: acc.chunks,
        reasoning_steps: acc.reasoningSteps,
        visualization_data: acc.visualizationData,
      });
    case 'answer_found':
      if (data.answer) {
        acc.answerParts.push(data.answer);
        callbacks?.onToken?.(data.answer);
      }
      break;
    case 'status':
      callbacks?.onStatus?.(data.progress, data.message);
      break;
    case 'error':
      callbacks?.onError?.(new Error(data.message));
      return Promise.reject(new Error(data.message));
  }
  return null;
}

// ─── Question Answering (SSE) ───
export async function askQuestionStream(
  kbId: string,
  fileId: string,
  question: string,
  clientId: string,
  callbacks?: StreamCallbacks,
): Promise<QuestionResult> {
  const body = { question, file_id: fileId };
  const params = new URLSearchParams({ client_id: clientId });
  const acc = createStreamAccumulator();

  return new Promise((resolve, reject) => {
    streamRequestClient(
      `/rag/api/knowledge-base/${kbId}/files/${fileId}/ask-question?${params}`,
      body,
      {
        onData: (data: any) => {
          const result = handleStreamEvent(data, acc, callbacks);
          if (result) result.then(resolve).catch(reject);
        },
        onError: (err) => { callbacks?.onError?.(err); reject(err); },
        onComplete: () => callbacks?.onComplete?.(),
      },
    );
  });
}

// ─── IRCoT Config ───
export async function getIRCoTStatusApi() {
  return requestClient.get<IRCoTConfig>('/rag/api/config/ircot');
}

export async function setIRCoTEnabledApi(enable: boolean) {
  return requestClient.post('/rag/api/config/ircot', { enable });
}

// ─── Chat / Conversation API ───
export async function createConversationApi(data: {
  title?: string;
  model_name?: string;
}) {
  return requestClient.post<ChatConversation>(
    '/rag/chat/conversation/create',
    data,
  );
}

export async function getUserConversationsApi(
  page?: number,
  pageSize?: number,
) {
  const params: Record<string, any> = {};
  if (page) params.page = page;
  if (pageSize) params.pageSize = pageSize;
  return requestClient.get<ChatConversation[]>(
    '/rag/chat/conversations',
    { params },
  );
}

export async function getChatHistoryApi(conversationId: string) {
  return requestClient.get<ChatMessage[]>(
    `/rag/chat/history/${conversationId}`,
  );
}

export async function deleteConversationApi(conversationId: string) {
  return requestClient.delete(
    `/rag/chat/conversation/${conversationId}`,
  );
}

export async function chatCompletionStream(
  data: {
    user_id: string;
    conversation_id?: string;
    question: string;
    model_name?: string;
    file_id?: string;
    kb_id?: string;
  },
  callbacks?: StreamCallbacks,
): Promise<QuestionResult> {
  const acc = createStreamAccumulator();

  return new Promise((resolve, reject) => {
    streamRequestClient('/rag/chat/message/chat', data, {
      onData: (d: any) => {
        const result = handleStreamEvent(d, acc, callbacks);
        if (result) result.then(resolve).catch(reject);
      },
      onError: (err) => { callbacks?.onError?.(err); reject(err); },
      onComplete: () => callbacks?.onComplete?.(),
    });
  });
}

// ─── Triple Management ───
export async function updateNodeCategoryApi(
  kbId: string,
  fileId: string,
  nodeName: string,
  newCategory: string,
) {
  return requestClient.put<GraphData>(
    `/rag/api/knowledge-base/${kbId}/files/${fileId}/graph/node/category`,
    { node_name: nodeName, new_category: newCategory },
  );
}

export async function addGraphEdgesApi(
  kbId: string,
  fileId: string,
  edges: {
    source: string;
    relation: string;
    target: string;
    source_category?: string;
    target_category?: string;
  }[],
) {
  return requestClient.post<GraphData>(
    `/rag/api/knowledge-base/${kbId}/files/${fileId}/graph/edges`,
    { edges },
  );
}

export async function addGraphNodesApi(
  kbId: string,
  fileId: string,
  nodes: { name: string; category?: string }[],
) {
  return requestClient.post<GraphData>(
    `/rag/api/knowledge-base/${kbId}/files/${fileId}/graph/nodes`,
    { nodes },
  );
}

export async function deleteGraphNodeApi(
  kbId: string,
  fileId: string,
  nodeName: string,
) {
  return requestClient.delete<GraphData>(
    `/rag/api/knowledge-base/${kbId}/files/${fileId}/graph/nodes/${encodeURIComponent(nodeName)}`,
  );
}

export async function deleteGraphEdgeApi(
  kbId: string,
  fileId: string,
  source: string,
  relation: string,
  target: string,
) {
  return requestClient.delete<GraphData>(
    `/rag/api/knowledge-base/${kbId}/files/${fileId}/graph/edge`,
    { data: { source, relation, target } },
  );
}

export interface GraphEdgeUpdatePayload {
  source: string;
  relation: string;
  target: string;
  new_source?: string;
  new_relation?: string;
  new_target?: string;
  new_source_category?: string;
  new_target_category?: string;
}

export async function updateGraphEdgeApi(
  kbId: string,
  fileId: string,
  data: GraphEdgeUpdatePayload,
) {
  return requestClient.put<GraphData>(
    `/rag/api/knowledge-base/${kbId}/files/${fileId}/graph/edge`,
    data,
  );
}

// ─── KB Permission Management ───
export async function getRolesApi() {
  return requestClient.get<{ id: string; name: string; code: string }[]>(
    '/rag/api/knowledge-base/roles',
  );
}

export async function getRoleKbPermissionsApi(roleId: string) {
  return requestClient.get<KnowledgeBaseListResult>(
    `/rag/api/knowledge-base/role/${roleId}/kb-permissions`,
  );
}

export async function updateRoleKbPermissionsApi(
  roleId: string,
  kbIds: string[],
) {
  return requestClient.put(
    `/rag/api/knowledge-base/role/${roleId}/kb-permissions`,
    { kb_ids: kbIds },
  );
}

// ─── Department APIs (for permission selector) ───
export async function getDepartmentsApi() {
  return requestClient.get<{ id: string; name: string }[]>(
    '/rag/api/knowledge-base/departments',
  );
}

export async function getDeptKbPermissionsApi(deptId: string) {
  return requestClient.get<KnowledgeBaseListResult>(
    `/rag/api/knowledge-base/dept/${deptId}/kb-permissions`,
  );
}

export async function updateDeptKbPermissionsApi(
  deptId: string,
  kbIds: string[],
) {
  return requestClient.put(
    `/rag/api/knowledge-base/dept/${deptId}/kb-permissions`,
    { kb_ids: kbIds },
  );
}

// ─── User APIs (for permission selector) ───
export async function getUsersApi(name?: string) {
  const params: Record<string, any> = {};
  if (name) params.name = name;
  return requestClient.get<{ id: string; name: string; username: string }[]>(
    '/rag/api/knowledge-base/users',
    { params },
  );
}

export async function getUserKbPermissionsApi(userId: string) {
  return requestClient.get<KnowledgeBaseListResult>(
    `/rag/api/knowledge-base/user/${userId}/kb-permissions`,
  );
}

export async function updateUserKbPermissionsApi(
  userId: string,
  kbIds: string[],
) {
  return requestClient.put(
    `/rag/api/knowledge-base/user/${userId}/kb-permissions`,
    { kb_ids: kbIds },
  );
}

// ─── KB-centric Permission APIs ───
export async function getKbPermissionsApi(kbId: string) {
  return requestClient.get<{
    role_ids: string[];
    dept_ids: string[];
    user_ids: string[];
    is_public: boolean;
  }>(`/rag/api/knowledge-base/${kbId}/permissions`);
}

export async function updateKbPermissionsApi(
  kbId: string,
  data: {
    role_ids?: string[];
    dept_ids?: string[];
    user_ids?: string[];
    is_public?: boolean;
  },
) {
  return requestClient.put(
    `/rag/api/knowledge-base/${kbId}/permissions`,
    data,
  );
}

// ─── File Preview ───
export function getKbFilePreviewUrl(kbId: string, fileId: string, token: string): string {
  return `/basic-api/rag/api/knowledge-base/${kbId}/files/${fileId}/preview?token=${token}`;
}

export async function getKbFilePreviewBlob(kbId: string, fileId: string, token: string): Promise<Blob> {
  const resp = await fetch(
    `/basic-api/rag/api/knowledge-base/${kbId}/files/${fileId}/preview?token=${token}`,
  );
  if (!resp.ok) throw new Error(`Preview fetch failed: ${resp.status}`);
  return resp.blob();
}

export async function getKbFileContentApi(kbId: string, fileId: string) {
  return requestClient.get<{ content: string; filename: string }>(
    `/rag/api/knowledge-base/${kbId}/files/${fileId}/content`,
  );
}

// ─── Status ───
export async function getRagStatusApi() {
  return requestClient.get('/rag/api/status');
}

// ─── AI Writing Types ───
export interface WriterConversation {
  id: string;
  title: string;
  user_id: string;
  model_name?: string;
  sys_create_datetime: string;
  sys_update_datetime: string;
}

export interface WriterConversationListResult {
  items: WriterConversation[];
  total: number;
}

export interface WriterMessage {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  model_name?: string;
  sys_create_datetime: string;
}

export interface WriterMessageListResult {
  items: WriterMessage[];
  total: number;
}

// ─── AI Writing ───
export async function createWriterConversationApi(data: {
  title?: string;
  model_name?: string;
}) {
  return requestClient.post<WriterConversation>(
    '/rag/api/ai-writing/conversation/create',
    data,
  );
}

export async function getWriterConversationsApi(params?: {
  page?: number;
  pageSize?: number;
}) {
  return requestClient.get<WriterConversationListResult>(
    '/rag/api/ai-writing/conversations',
    { params },
  );
}

export async function getWriterConversationApi(id: string) {
  return requestClient.get<WriterConversation>(
    `/rag/api/ai-writing/conversation/${id}`,
  );
}

export async function deleteWriterConversationApi(id: string) {
  return requestClient.delete(`/rag/api/ai-writing/conversation/${id}`);
}

export async function updateWriterConversationTitleApi(
  id: string,
  title: string,
) {
  return requestClient.put<WriterConversation>(
    `/rag/api/ai-writing/conversation/${id}/title`,
    { title },
  );
}

export async function getWriterMessagesApi(conversationId: string) {
  return requestClient.get<WriterMessageListResult>(
    `/rag/api/ai-writing/conversation/${conversationId}/messages`,
  );
}

export async function updateWriterMessageApi(
  conversationId: string,
  messageId: string,
  content: string,
) {
  return requestClient.put<WriterMessage>(
    `/rag/api/ai-writing/conversation/${conversationId}/message/${messageId}`,
    { content },
  );
}

export async function aiEditMessageStream(
  conversationId: string,
  messageId: string,
  content: string,
  instruction: 'polish' | 'rewrite' | 'custom',
  customPrompt?: string,
  callbacks?: {
    onToken?: (token: string) => void;
    onDone?: (fullText: string) => void;
    onError?: (error: Error) => void;
  },
) {
  return streamRequestClient(
    `/rag/api/ai-writing/conversation/${conversationId}/message/${messageId}/ai-edit`,
    { content, instruction, custom_prompt: customPrompt },
    {
      onData: (data: any) => {
        switch (data.type) {
          case 'token':
            callbacks?.onToken?.(data.text ?? data.content ?? '');
            break;
          case 'done':
            callbacks?.onDone?.(data.answer ?? data.content ?? '');
            break;
          case 'error':
            callbacks?.onError?.(new Error(data.message));
            break;
        }
      },
      onError: (err) => callbacks?.onError?.(err),
    },
  );
}

// ─── AI Writing Document Types ───
export interface WriterDocument {
  id: string;
  conversation_id: string;
  message_id: string;
  title: string;
  content: string;
  sys_create_datetime: string;
  sys_update_datetime: string;
}

export interface WriterDocumentListResult {
  items: WriterDocument[];
  total: number;
}

// ─── AI Writing Document APIs ───
export async function createWriterDocumentApi(
  conversationId: string,
  messageId: string,
  title: string,
  content: string,
) {
  return requestClient.post<WriterDocument>(
    `/rag/api/ai-writing/conversation/${conversationId}/message/${messageId}/document`,
    { title, content },
  );
}

export async function getWriterConversationDocumentsApi(conversationId: string) {
  return requestClient.get<WriterDocumentListResult>(
    `/rag/api/ai-writing/conversation/${conversationId}/documents`,
  );
}

export async function getWriterDocumentApi(documentId: string) {
  return requestClient.get<WriterDocument>(
    `/rag/api/ai-writing/document/${documentId}`,
  );
}

export async function updateWriterDocumentApi(
  documentId: string,
  data: { title?: string; content?: string },
) {
  return requestClient.put<WriterDocument>(
    `/rag/api/ai-writing/document/${documentId}`,
    data,
  );
}

export async function deleteWriterDocumentApi(documentId: string) {
  return requestClient.delete(`/rag/api/ai-writing/document/${documentId}`);
}

export async function aiWritingStream(
  question: string,
  conversationId?: string,
  history?: { role: string; content: string }[],
  callbacks?: {
    onToken?: (token: string) => void;
    onDone?: (fullText: string, convId?: string, messageId?: string) => void;
    onError?: (error: Error) => void;
  },
) {
  const body: Record<string, any> = { question };
  if (conversationId) {
    body.conversation_id = conversationId;
  }
  if (history && history.length > 0) {
    body.history = history;
  }
  return streamRequestClient(
    '/rag/api/ai-writing/chat',
    body,
    {
      onData: (data: any) => {
        switch (data.type) {
          case 'token':
            callbacks?.onToken?.(data.text ?? data.content ?? '');
            break;
          case 'done':
            callbacks?.onDone?.(data.answer ?? data.content ?? '', data.conversation_id, data.message_id);
            break;
          case 'error':
            callbacks?.onError?.(new Error(data.message));
            break;
        }
      },
      onError: (err) => callbacks?.onError?.(err),
    },
  );
}

// ─── Chronicle Writer ───

export interface ChronicleInterruptDecision {
  action: 'retry' | 'override' | 'skip';
  override_data?: Record<string, any>;
}

export interface ChronicleChatRequest {
  conversation_id?: string;
  question: string;
  kb_ids: string[];
  project_config?: Record<string, any>;
  interrupt_decision?: ChronicleInterruptDecision;
}

// ─── 项目详情 ───

export interface SectionNode {
  id: string;
  title: string;
  level: number;
  sort_order: number;
  content: string;
  word_count: number;
  status: string;
  children: SectionNode[];
}

export interface ReviewItem {
  id: string;
  section_id: string | null;
  review_type: string;
  severity: string;
  issue: string;
  suggestion: string | null;
  resolved: boolean;
}

export interface LogEntry {
  stage: string;
  event_type: string;
  message: string | null;
  created_at: string;
}

export interface ProjectDetail {
  id: string;
  title: string;
  chronicle_type: string;
  region_name: string | null;
  scope_description: string | null;
  status: string;
  word_count: number;
  report: string | null;
  conversation_id: string | null;
  sections: SectionNode[];
  review_summary: Record<string, number>;
  created_at: string;
}

export function getChronicleProjectApi(projectId: string): Promise<ProjectDetail> {
  return requestClient.get(`/api/chronicle/project/${projectId}`);
}

export function getChronicleSectionsApi(projectId: string): Promise<{ items: SectionNode[]; total: number }> {
  return requestClient.get(`/api/chronicle/project/${projectId}/sections`);
}

export function getChronicleReviewsApi(projectId: string): Promise<{ items: ReviewItem[]; total: number }> {
  return requestClient.get(`/api/chronicle/project/${projectId}/reviews`);
}

export function getChronicleLogApi(projectId: string): Promise<{ items: LogEntry[]; total: number }> {
  return requestClient.get(`/api/chronicle/project/${projectId}/log`);
}

export async function chronicleChatStream(
  data: ChronicleChatRequest,
  callbacks?: {
    onToken?: (token: string) => void;
    onStatus?: (stage: string, progress: number, message: string) => void;
    onInterrupt?: (data: any) => void;
    onDone?: (fullText: string, convId?: string, extra?: { project_id?: string; report?: string; report_details?: any[]; kg_data?: any }) => void;
    onError?: (error: Error) => void;
  },
) {
  return streamRequestClient('/api/chronicle/chat', data, {
    onData: (event: any) => {
      switch (event.type) {
        case 'token':
          callbacks?.onToken?.(event.text ?? '');
          break;
        case 'status':
          callbacks?.onStatus?.(event.stage, event.progress, event.message);
          break;
        case 'interrupt':
          callbacks?.onInterrupt?.(event);
          break;
        case 'done':
          callbacks?.onDone?.(
            event.content ?? '',
            event.conversation_id,
            {
              project_id: event.project_id,
              report: event.report,
              report_details: event.report_details,
              kg_data: event.kg_data,
            },
          );
          break;
        case 'error':
          callbacks?.onError?.(new Error(event.message));
          break;
      }
    },
    onError: (err) => callbacks?.onError?.(err),
  });
}

export async function aiEditStream(
  content: string,
  instruction: 'polish' | 'rewrite' | 'custom',
  customPrompt?: string,
  callbacks?: {
    onToken?: (token: string) => void;
    onDone?: (fullText: string) => void;
    onError?: (error: Error) => void;
  },
) {
  return streamRequestClient(
    '/rag/api/ai-writing/edit',
    { content, instruction, custom_prompt: customPrompt },
    {
      onData: (data: any) => {
        switch (data.type) {
          case 'token':
            callbacks?.onToken?.(data.text ?? data.content ?? '');
            break;
          case 'done':
            callbacks?.onDone?.(data.answer ?? data.content ?? '');
            break;
          case 'error':
            callbacks?.onError?.(new Error(data.message));
            break;
        }
      },
      onError: (err) => callbacks?.onError?.(err),
    },
  );
}
