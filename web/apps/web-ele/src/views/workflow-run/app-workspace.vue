<script setup lang="ts">
import type { WorkflowDef, WorkflowInstance } from '#/api/core/ai-workflow';

import { marked } from 'marked';
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { ArrowLeft } from '@vben/icons';

import { extractResultText } from '#/utils/workflow';

import {
  ElAlert,
  ElButton,
  ElEmpty,
  ElInput,
  ElMessage,
  ElTag,
  ElTooltip,
} from 'element-plus';

import {
  getPublishedWorkflowByRouteApi,
  getWorkflowInstanceApi,
  getWorkflowInstancesApi,
  runWorkflowApi,
  streamWorkflowInstanceApi,
} from '#/api/core/ai-workflow';
import { getNodeMeta } from '#/views/_core/ai-workflow/editor/nodes/index';

defineOptions({ name: 'AppWorkflowWorkspace' });

const route = useRoute();
const router = useRouter();

// 工作流
const workflow = ref<WorkflowDef | null>(null);
const loadingMeta = ref(true);

// 输入表单
interface InputFieldDef {
  key: string;
  label: string;
}
const inputFields = ref<InputFieldDef[]>([]);
const formModel = ref<Record<string, any>>({});

// 执行状态
const executing = ref(false);
const instanceId = ref<string | null>(null);
const nodeStatuses = ref<Record<string, NodeStatus>>({});
interface NodeStatus {
  status: 'pending' | 'running' | 'completed' | 'error';
  nodeType: string;
  duration?: number;
}

// 结果
const resultText = ref('');
const execError = ref('');
const showResult = ref(false);
const selectedHistoryId = ref<string | null>(null);

// 历史
const instances = ref<WorkflowInstance[]>([]);

// SSE
let activeStream: { abort: () => void } | null = null;

function goBack() {
  router.push('/ai-platform/workflow');
}

function discoverInputFields() {
  if (!workflow.value) return;
  const vars = new Set<string>();
  for (const node of workflow.value.nodes || []) {
    try {
      const str = JSON.stringify(node.params);
      const matches = str.matchAll(/\${_input\.([^}]+)}/g);
      for (const m of matches) {
        if (m[1]) vars.add(m[1]);
      }
    } catch {
      // 忽略单个节点解析错误
    }
  }
  inputFields.value = [...vars].map((key) => ({ key, label: key }));
  for (const f of inputFields.value) {
    formModel.value[f.key] = '';
  }
}

async function handleExecute() {
  if (!workflow.value) return;
  executing.value = true;
  execError.value = '';
  resultText.value = '';
  showResult.value = false;
  selectedHistoryId.value = null;
  nodeStatuses.value = {};

  try {
    const inst = await runWorkflowApi(workflow.value.id, formModel.value);
    instanceId.value = inst.id;

    const stream = streamWorkflowInstanceApi(inst.id, {
      onNodeStart(data) {
        nodeStatuses.value[data.node_id] = {
          status: 'running',
          nodeType: data.node_type,
        };
        nodeStatuses.value = { ...nodeStatuses.value };
      },
      onNodeComplete(data) {
        const ns = nodeStatuses.value[data.node_id];
        if (ns) {
          ns.status = data.error ? 'error' : 'completed';
          ns.duration = data.duration_ms;
          nodeStatuses.value = { ...nodeStatuses.value };
        }
      },
      onNodeError(data) {
        const ns = nodeStatuses.value[data.node_id];
        if (ns) {
          ns.status = 'error';
          nodeStatuses.value = { ...nodeStatuses.value };
        }
      },
      onWorkflowComplete(data) {
        resultText.value = extractResultText(data.result);
        showResult.value = true;
      },
      onWorkflowError(data) {
        execError.value = data.error || '执行失败';
        showResult.value = true;
      },
      onError(err) {
        ElMessage.error(err.message);
      },
      onComplete() {
        executing.value = false;
        activeStream = null;
        loadHistory();
      },
    });
    activeStream = stream;
  } catch {
    ElMessage.error('启动工作流失败');
    executing.value = false;
  }
}

function cancelExecution() {
  activeStream?.abort();
  activeStream = null;
  executing.value = false;
}

function renderMarkdown(text: string): string {
  return marked.parse(text, { async: false }) as string;
}

function getNodeLabel(type: string): string {
  return getNodeMeta(type)?.label || type;
}

function statusIcon(s: string): string {
  switch (s) {
    case 'pending':
      return '\u23F3';
    case 'running':
      return '\uD83D\uDD04';
    case 'completed':
      return '\u2705';
    case 'error':
      return '\u274C';
    default:
      return '\u23F3';
  }
}

function statusText(s: string): string {
  switch (s) {
    case 'pending':
      return '等待中';
    case 'running':
      return '运行中...';
    case 'completed':
      return '已完成';
    case 'error':
      return '失败';
    default:
      return '';
  }
}

async function loadHistory() {
  if (!workflow.value) return;
  try {
    const res = await getWorkflowInstancesApi({
      defId: workflow.value.id,
      page: 1,
      pageSize: 10,
    });
    instances.value = res.items || [];
  } catch {
    // 静默
  }
}

async function viewHistory(inst: WorkflowInstance) {
  if (inst.id === selectedHistoryId.value) return;
  selectedHistoryId.value = inst.id;
  execError.value = '';
  showResult.value = true;
  resultText.value = '';
  try {
    const detail = await getWorkflowInstanceApi(inst.id);
    if (detail) {
      resultText.value = extractResultText(detail.output_result);
      execError.value = detail.error || '';
    }
  } catch {
    ElMessage.error('加载历史记录失败');
  }
}

function formatTime(dateStr?: string): string {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const h = String(d.getHours()).padStart(2, '0');
    const min = String(d.getMinutes()).padStart(2, '0');
    return `${y}-${m}-${day} ${h}:${min}`;
  } catch {
    return dateStr;
  }
}

function statusLabel(s: string): string {
  const map: Record<string, string> = {
    completed: '成功',
    failed: '失败',
    cancelled: '已取消',
    running: '运行中',
    pending: '等待中',
  };
  return map[s] || s;
}

onMounted(async () => {
  const routeStr = route.params.route as string;
  try {
    workflow.value = await getPublishedWorkflowByRouteApi(routeStr);
    discoverInputFields();
    await loadHistory();
  } catch {
    ElMessage.error('工作流不存在或未发布');
    router.push('/');
    return;
  } finally {
    loadingMeta.value = false;
  }
});

onBeforeUnmount(() => {
  activeStream?.abort();
});
</script>

<template>
  <div class="app-workspace" v-loading="loadingMeta">
    <!-- Header -->
    <header class="workspace-header">
      <div class="workspace-header__left">
        <ElTooltip content="返回" placement="bottom">
          <ElButton text @click="goBack">
            <ArrowLeft class="h-4 w-4" />
          </ElButton>
        </ElTooltip>
        <span class="workspace-header__title">{{ workflow?.name || '应用工作流' }}</span>
        <ElTag type="warning" size="small" effect="light">应用</ElTag>
      </div>
    </header>

    <div class="workspace-body">
      <!-- 执行区：表单 + 按钮 -->
      <section class="exec-section">
        <div v-if="inputFields.length > 0" class="form-area">
          <div v-for="field in inputFields" :key="field.key" class="form-row">
            <label class="form-label">{{ field.label }}</label>
            <ElInput
              v-model="formModel[field.key]"
              :placeholder="'请输入 ' + field.label"
              :disabled="executing"
            />
          </div>
        </div>
        <div class="action-row">
          <ElButton
            type="primary"
            :loading="executing"
            :disabled="executing"
            @click="handleExecute"
          >
            <svg
              class="btn-icon" width="16" height="16" viewBox="0 0 24 24"
              fill="none" stroke="currentColor" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round"
            >
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
            开始执行
          </ElButton>
          <ElButton v-if="executing" @click="cancelExecution">停止</ElButton>
        </div>
      </section>

      <!-- 进度区 -->
      <section v-if="Object.keys(nodeStatuses).length > 0" class="progress-section">
        <h3 class="section-title">执行进度</h3>
        <div class="node-list">
          <div
            v-for="(ns, nid) in nodeStatuses"
            :key="nid"
            class="node-item"
            :class="'node-' + ns.status"
          >
            <span class="node-icon">{{ statusIcon(ns.status) }}</span>
            <span class="node-name">{{ getNodeLabel(ns.nodeType) }}</span>
            <span class="node-duration">{{
              ns.duration ? ns.duration + 'ms' : statusText(ns.status)
            }}</span>
          </div>
        </div>
      </section>

      <!-- 结果区 -->
      <section v-if="showResult" class="result-section">
        <h3 v-if="resultText || execError" class="section-title">执行结果</h3>
        <ElAlert v-if="execError" type="error" :title="execError" show-icon :closable="false" />
        <div v-if="resultText" class="md-content" v-html="renderMarkdown(resultText)" />
      </section>

      <!-- 历史记录 -->
      <section class="history-section">
        <h3 class="section-title">执行记录</h3>
        <div v-if="instances.length === 0" class="history-empty">
          <ElEmpty description="暂无执行记录" />
        </div>
        <div v-else class="history-list">
          <div
            v-for="inst in instances"
            :key="inst.id"
            class="history-item"
            :class="{ 'is-active': inst.id === selectedHistoryId }"
            @click="viewHistory(inst)"
          >
            <span class="h-status">{{
              inst.status === 'completed'
                ? '\u2705'
                : inst.status === 'failed'
                  ? '\u274C'
                  : '\u23F3'
            }}</span>
            <span class="h-time">{{ formatTime(inst.sys_create_datetime) }}</span>
            <span class="h-status-text" :class="'h-' + inst.status">{{
              statusLabel(inst.status)
            }}</span>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
/* ── 全屏容器 ── */
.app-workspace {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--el-bg-color);
}

/* ── Header ── */
.workspace-header {
  height: 52px;
  display: flex;
  align-items: center;
  padding: 0 16px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
  z-index: 20;
}

.workspace-header__left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.workspace-header__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Body ── */
.workspace-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px 0;
}

/* ── 各 section 通用 ── */
.exec-section,
.progress-section,
.result-section,
.history-section {
  width: min(800px, 80%);
  margin: 0 auto 32px;
}

.section-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

/* ── 执行区 ── */
.form-area {
  margin-bottom: 16px;
}

.form-row {
  margin-bottom: 14px;
}

.form-label {
  display: block;
  margin-bottom: 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.action-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.btn-icon {
  margin-right: 4px;
  vertical-align: middle;
}

/* ── 进度区 ── */
.node-list {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}

.node-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  font-size: 13px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  transition: background 0.12s;
}

.node-item:last-child {
  border-bottom: none;
}

.node-icon {
  flex-shrink: 0;
  width: 20px;
  text-align: center;
}

.node-name {
  flex: 1;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.node-duration {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  white-space: nowrap;
}

.node-item.node-completed {
  background: var(--el-color-success-light-9);
}

.node-item.node-error {
  background: var(--el-color-danger-light-9);
}

.node-item.node-running {
  background: var(--el-color-primary-light-9);
}

/* ── 结果区 ── */
.result-section .md-content {
  padding: 16px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
  line-height: 1.6;
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.result-section .el-alert {
  margin-bottom: 12px;
}

/* ── Markdown ── */
.md-content :deep(p) {
  margin: 0 0 8px;
}

.md-content :deep(p:last-child) {
  margin-bottom: 0;
}

.md-content :deep(code) {
  background: var(--el-fill-color);
  padding: 1px 4px;
  border-radius: 4px;
  font-size: 12px;
}

.md-content :deep(pre) {
  background: #1e293b;
  color: #e2e8f0;
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 12px;
  margin: 8px 0;
}

.md-content :deep(pre code) {
  background: transparent;
  padding: 0;
  color: inherit;
}

.md-content :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
  font-size: 12px;
}

.md-content :deep(th),
.md-content :deep(td) {
  border: 1px solid var(--el-border-color-lighter);
  padding: 6px 10px;
  text-align: left;
}

.md-content :deep(th) {
  background: var(--el-fill-color-lighter);
  font-weight: 600;
}

.md-content :deep(ul),
.md-content :deep(ol) {
  padding-left: 20px;
  margin: 4px 0;
}

.md-content :deep(blockquote) {
  border-left: 3px solid var(--el-border-color);
  padding-left: 12px;
  color: var(--el-text-color-secondary);
  margin: 8px 0;
}

.md-content :deep(h1),
.md-content :deep(h2),
.md-content :deep(h3),
.md-content :deep(h4) {
  margin: 12px 0 8px;
  font-weight: 600;
}

.md-content :deep(h1) {
  font-size: 16px;
}
.md-content :deep(h2) {
  font-size: 15px;
}
.md-content :deep(h3) {
  font-size: 14px;
}
.md-content :deep(h4) {
  font-size: 13px;
}

/* ── 历史记录 ── */
.history-list {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  cursor: pointer;
  border-bottom: 1px solid var(--el-border-color-lighter);
  transition: background 0.12s;
  font-size: 13px;
}

.history-item:last-child {
  border-bottom: none;
}

.history-item:hover {
  background: var(--el-fill-color-lighter);
}

.history-item.is-active {
  background: var(--el-color-primary-light-9);
}

.h-status {
  flex-shrink: 0;
  width: 20px;
  text-align: center;
}

.h-time {
  flex: 1;
  color: var(--el-text-color-primary);
}

.h-status-text {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.h-status-text.h-completed {
  color: var(--el-color-success);
}

.h-status-text.h-failed {
  color: var(--el-color-danger);
}

.history-empty {
  padding: 24px 0;
}
</style>
