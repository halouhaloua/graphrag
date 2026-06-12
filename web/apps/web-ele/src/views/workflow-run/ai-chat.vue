<script setup lang="ts">
import type {
  WorkflowConversation,
  WorkflowDef,
} from '#/api/core/ai-workflow';

import { marked } from 'marked';
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { ArrowLeft, Plus, Trash2 } from '@vben/icons';

import { extractResultText } from '#/utils/workflow';

import {
  ElButton,
  ElInput,
  ElMessage,
  ElMessageBox,
  ElTag,
  ElTooltip,
} from 'element-plus';

import {
  createConversationApi,
  deleteConversationApi,
  getConversationApi,
  getPublishedWorkflowByRouteApi,
  listConversationsApi,
  sendTurnStreamApi,
} from '#/api/core/ai-workflow';

defineOptions({ name: 'AiWorkflowChat' });

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
}

const route = useRoute();
const router = useRouter();

// 工作流
const workflow = ref<WorkflowDef | null>(null);
const loading = ref(true);

// 会话
const conversations = ref<WorkflowConversation[]>([]);
const currentConvId = ref<string>('');

// 聊天
const messages = ref<ChatMessage[]>([]);
const inputText = ref('');
const streaming = ref(false);
let abortStream: { abort: () => void } | null = null;
let assistantMsg: ChatMessage | null = null;

async function loadWorkflow() {
  const routeStr = route.params.route as string;
  try {
    workflow.value = await getPublishedWorkflowByRouteApi(routeStr);
  } catch {
    ElMessage.error('工作流不存在或未发布');
    router.push('/');
    return;
  }
}

async function loadConversations() {
  if (!workflow.value) return;
  const res = await listConversationsApi({
    defId: workflow.value.id,
    pageSize: 50,
  });
  conversations.value = res.items || [];
}

function startNewConversation() {
  currentConvId.value = '';
  messages.value = [];
}

async function switchConversation(convId: string) {
  currentConvId.value = convId;
  messages.value = [];
  const detail = await getConversationApi(convId);
  if (!detail) return;
  for (const t of detail.turns || []) {
    messages.value.push({
      id: `turn-${t.turn_index}-user`,
      role: 'user',
      content: t.input_message,
    });
    const aiContent = extractResultText(t.output_result);
    if (aiContent) {
      messages.value.push({
        id: `turn-${t.turn_index}-ai`,
        role: 'assistant',
        content: aiContent,
      });
    }
  }
}

async function deleteConv(convId: string, ev: Event) {
  ev.stopPropagation();
  try {
    await ElMessageBox.confirm('确定删除此对话？', '删除确认');
    await deleteConversationApi(convId);
    conversations.value = conversations.value.filter(
      (c) => c.id !== convId,
    );
    if (currentConvId.value === convId) {
      currentConvId.value = '';
      messages.value = [];
    }
  } catch {
    // 取消
  }
}

async function sendMessage() {
  const text = inputText.value.trim();
  if (!text || !workflow.value) return;

  // 不存在当前会话时，发送第一条消息时创建
  if (!currentConvId.value) {
    const conv = await createConversationApi(workflow.value.id);
    conversations.value.unshift(conv);
    currentConvId.value = conv.id;
    await loadConversations();
  }

  inputText.value = '';
  messages.value.push({
    id: `msg-${Date.now()}`,
    role: 'user',
    content: text,
  });

  streaming.value = true;
  assistantMsg = {
    id: `msg-${Date.now()}-ai`,
    role: 'assistant',
    content: '',
    streaming: true,
  };
  messages.value.push(assistantMsg);

  abortStream = sendTurnStreamApi(currentConvId.value, text, {
    onToken(token: string) {
      if (assistantMsg) {
        assistantMsg.content += token;
        messages.value = [...messages.value];
      }
    },
    onDone(result?: any) {
      if (assistantMsg) {
        if (!assistantMsg.content) {
          const extracted = extractResultText(result);
          if (extracted) assistantMsg.content = extracted;
        }
        assistantMsg.streaming = false;
        messages.value = [...messages.value];
      }
    },
    onError(err: Error) {
      ElMessage.error(err.message);
      if (assistantMsg) {
        assistantMsg.streaming = false;
        messages.value = [...messages.value];
      }
    },
    onComplete() {
      streaming.value = false;
      loadConversations().catch(() => {});
    },
  });
}

function cancelStream() {
  abortStream?.abort();
  streaming.value = false;
  if (assistantMsg) {
    assistantMsg.streaming = false;
  }
}

function renderMarkdown(text: string): string {
  return marked.parse(text, { async: false }) as string;
}

const messagesContainer = ref<HTMLElement | null>(null);

function scrollToBottom() {
  const el = messagesContainer.value;
  if (el) {
    el.scrollTop = el.scrollHeight;
  }
}

const scrollKey = computed(() => {
  const len = messages.value.length;
  if (len === 0) return 0;
  return len + '-' + (messages.value[len - 1]?.content?.length ?? 0);
});

watch(scrollKey, () => { nextTick(scrollToBottom); }, { flush: 'post' });

function onKeydown(e: Event | KeyboardEvent) {
  const ke = e as KeyboardEvent;
  if (ke.key === 'Enter' && !ke.shiftKey) {
    ke.preventDefault();
    sendMessage();
  }
}

onMounted(async () => {
  await loadWorkflow();
  loading.value = false;
  if (workflow.value) {
    await loadConversations();
    // 默认进入第一个会话，若无则自动创建
    const first = conversations.value[0];
    if (first) {
      await switchConversation(first.id);
    } else {
      await startNewConversation();
    }
  }
});

onBeforeUnmount(() => {
  abortStream?.abort();
});
</script>

<template>
  <div class="ai-chat" v-loading="loading">
    <!-- Header -->
    <header class="chat-header">
      <div class="chat-header__left">
        <ElTooltip content="返回" placement="bottom">
          <ElButton text @click="router.push('/ai-platform/workflow')">
            <ArrowLeft class="h-4 w-4" />
          </ElButton>
        </ElTooltip>
        <span class="chat-header__title">{{ workflow?.name || 'AI 工作流' }}</span>
        <ElTag type="primary" size="small" effect="light">AI</ElTag>
      </div>
    </header>

    <div class="chat-body">
      <!-- 会话侧栏 -->
      <aside class="chat-sidebar">
        <div class="sidebar-header">
          <span class="sidebar-title">对话</span>
          <ElButton size="small" type="primary" plain @click="startNewConversation">
            <Plus class="h-3.5 w-3.5" />新对话
          </ElButton>
        </div>
        <ElScrollbar class="sidebar-list">
          <div
            v-for="conv in conversations"
            :key="conv.id"
            class="sidebar-item"
            :class="{ 'is-active': conv.id === currentConvId }"
            @click="switchConversation(conv.id)"
          >
            <div class="sidebar-item__info">
              <div class="sidebar-item__title">{{ conv.title || '新对话' }}</div>
              <div class="sidebar-item__meta">{{ conv.turn_count }} 轮</div>
            </div>
            <ElButton
              text
              size="small"
              class="sidebar-item__del"
              @click="deleteConv(conv.id, $event)"
            >
              <Trash2 class="h-3 w-3" />
            </ElButton>
          </div>
          <div v-if="conversations.length === 0" class="sidebar-empty">
            暂无对话
          </div>
        </ElScrollbar>
      </aside>

      <!-- 主聊天区 -->
      <main class="chat-main">
        <div class="chat-messages" ref="messagesContainer">
          <!-- 空状态 -->
          <div v-if="messages.length === 0" class="empty-state">
            <div class="empty-icon">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" stroke-width="1.5"
                stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <p>输入问题开始对话</p>
          </div>

          <!-- 消息列表 -->
          <div
            v-for="msg in messages"
            :key="msg.id"
            class="message-row"
            :class="msg.role"
          >
            <div v-if="msg.role === 'user'" class="message-content">
              <div class="bubble user-bubble">
                <div class="text">{{ msg.content }}</div>
              </div>
            </div>
            <div v-else class="message-content">
              <div class="answer-section">
                <div class="md-content" v-html="renderMarkdown(msg.content)"></div>
              </div>
            </div>
          </div>

          <!-- 流式指示器 -->
          <div v-if="streaming" class="streaming-indicator">
            <span class="dot-pulse"></span>
            <span>AI 正在思考...</span>
          </div>
        </div>

        <!-- 输入区 -->
        <div class="input-area">
          <div class="input-shell">
            <ElInput
              v-model="inputText"
              type="textarea"
              :rows="3"
              resize="none"
              placeholder="输入您的问题，Enter 发送，Shift+Enter 换行"
              :disabled="streaming"
              @keydown="onKeydown"
            />
            <div class="input-footer">
              <div class="footer-actions"></div>
              <ElButton
                type="primary"
                circle
                class="send-button"
                :disabled="!inputText.trim() || streaming"
                @click="sendMessage"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" stroke-width="2"
                  stroke-linecap="round" stroke-linejoin="round">
                  <path d="M22 2 11 13" />
                  <path d="M22 2 15 22 11 13 2 9 22 2z" />
                </svg>
              </ElButton>
              <ElButton
                v-if="streaming"
                size="small"
                @click="cancelStream"
              >
                停止
              </ElButton>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
/* ── 全屏容器 ── */
.ai-chat {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--el-bg-color);
}

/* ── Header ── */
.chat-header {
  height: 52px;
  display: flex;
  align-items: center;
  padding: 0 16px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
  z-index: 20;
}

.chat-header__left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.chat-header__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Body ── */
.chat-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}

/* ── 会话侧栏 ── */
.chat-sidebar {
  width: 240px;
  flex-shrink: 0;
  background: var(--el-bg-color-overlay);
  border-right: 1px solid var(--el-border-color-lighter);
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}

.sidebar-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.sidebar-list {
  flex: 1;
  padding: 4px 0;
}

.sidebar-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 14px;
  cursor: pointer;
  border-left: 3px solid transparent;
  transition: background 0.12s;
}

.sidebar-item:hover {
  background: var(--el-fill-color-lighter);
}

.sidebar-item.is-active {
  background: var(--el-color-primary-light-9);
  border-left-color: var(--el-color-primary);
}

.sidebar-item__info {
  flex: 1;
  min-width: 0;
}

.sidebar-item__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar-item__meta {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 1px;
}

.sidebar-item__del {
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.12s;
}

.sidebar-item:hover .sidebar-item__del {
  opacity: 1;
}

.sidebar-empty {
  text-align: center;
  padding: 24px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

/* ── 主聊天区 ── */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-messages {
  flex: 1;
  padding: 16px 0;
  overflow-y: auto;
  min-height: 0;
}

/* ── 空状态 ── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--el-text-color-secondary);
}

.empty-icon {
  margin-bottom: 12px;
  font-size: 48px;
}

/* ── 消息样式 ── */
.message-row {
  display: flex;
  margin-bottom: 16px;
  margin-left: auto;
  margin-right: auto;
  width: min(800px, 80%);
}

.message-row.user {
  justify-content: flex-end;
}

.message-row.assistant {
  justify-content: flex-start;
}

.message-content {
  min-width: 0;
  max-width: 85%;
}

.user .message-content {
  display: flex;
  width: auto;
  justify-content: flex-end;
  margin-left: auto;
}

.assistant .message-content {
  padding: 4px 0;
}

.answer-section {
  padding: 4px 0;
  line-height: 1.6;
}

.bubble {
  width: fit-content;
  max-width: 100%;
  padding: 10px 16px;
  font-size: 14px;
  line-height: 1.6;
  background: var(--el-fill-color-light);
  border-radius: 12px;
}

.user-bubble {
  background: var(--el-color-primary-light-8);
  border-bottom-right-radius: 4px;
  margin-left: auto;
}

.text {
  max-width: 100%;
  overflow-wrap: break-word;
  word-break: normal;
  white-space: pre-wrap;
}

.md-content {
  line-height: 1.6;
}

/* ── Markdown 渲染 ── */
.md-content :deep(p) {
  margin: 0 0 8px;
}

.md-content :deep(p:last-child) {
  margin-bottom: 0;
}

.md-content :deep(code) {
  background: var(--el-fill-color-lighter);
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

.md-content :deep(h1) { font-size: 16px; }
.md-content :deep(h2) { font-size: 15px; }
.md-content :deep(h3) { font-size: 14px; }
.md-content :deep(h4) { font-size: 13px; }

/* ── 流式指示器 ── */
.streaming-indicator {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 12px 0 8px;
  margin: 0 auto;
  width: min(800px, 80%);
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.dot-pulse {
  width: 8px;
  height: 8px;
  background: var(--el-color-primary);
  border-radius: 50%;
  animation: pulse 1.2s infinite;
  flex-shrink: 0;
}

@keyframes pulse {
  0%, 100% { opacity: 0.4; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.2); }
}

/* ── 输入区 ── */
.input-area {
  display: flex;
  justify-content: center;
  padding: 8px 0;
  background: var(--el-bg-color-overlay);
}

.input-shell {
  width: min(800px, 80%);
  padding: 8px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 16px;
  box-shadow: 0 10px 24px rgb(15 23 42 / 6%);
}

.input-shell :deep(.el-textarea__inner) {
  min-height: 48px !important;
  max-height: 120px;
  padding: 2px 4px;
  background: transparent;
  border: none;
  box-shadow: none;
}

.input-shell :deep(.el-textarea__inner:focus) {
  box-shadow: none;
}

.input-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}

.footer-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  min-width: 0;
}

.send-button {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
}
</style>
