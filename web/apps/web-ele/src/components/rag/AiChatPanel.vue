<script lang="ts" setup>
import { ref, watch, nextTick } from 'vue';
import { ElButton, ElInput } from 'element-plus';
import ChatMessageItem from '#/components/rag/ChatMessageItem.vue';
import type { WriterDocument } from '#/api/core/rag';

const props = defineProps<{
  messages: any[];
  streaming: boolean;
  placeholder?: string;
  editingMsgId?: string | null;
  documentsByMsgId?: Record<string, WriterDocument[]>;
  messagesVersion?: number;
  kbIds?: string[];
  selectedKbLabel?: string;
}>();

const emit = defineEmits<{
  send: [question: string];
  convert: [content: string, msgId: string];
  openDocument: [doc: WriterDocument];
  deleteDocument: [docId: string];
  openKbSelector: [];
}>();

const inputText = ref('');
const messagesContainer = ref<HTMLElement | null>(null);

function scrollToBottom() {
  const el = messagesContainer.value;
  if (el) {
    el.scrollTop = el.scrollHeight;
  }
}

function handleSend() {
  const text = inputText.value.trim();
  if (!text || props.streaming) return;
  inputText.value = '';
  emit('send', text);
}

function onKeydown(e: Event) {
  const ke = e as KeyboardEvent;
  if (ke.key === 'Enter' && !ke.shiftKey) {
    ke.preventDefault();
    handleSend();
  }
}

watch(
  () => props.messagesVersion,
  () => nextTick(scrollToBottom),
);

watch(
  () => props.messages[props.messages.length - 1]?.content,
  () => nextTick(scrollToBottom),
  { flush: 'post' },
);
</script>

<template>
  <div class="ai-chat-inner">
    <div ref="messagesContainer" class="messages-container">
      <div v-if="messages.length === 0" class="empty-state">
        <div class="empty-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        </div>
        <p>输入问题开始 AI 写作</p>
      </div>
      <div class="messages-shell">
        <ChatMessageItem
          v-for="msg in messages"
          :key="msg.id"
          :message="msg"
          :documents-by-msg-id="documentsByMsgId"
          @convert="emit('convert', $event, msg.id)"
          @open-document="emit('openDocument', $event)"
          @delete-document="emit('deleteDocument', $event)"
        />
        <div v-if="streaming" class="streaming-indicator">
          <span class="dot-pulse"></span>
          <span>AI 正在写作...</span>
        </div>
      </div>
    </div>

    <div class="input-area">
      <div class="input-shell">
        <el-input
          v-model="inputText"
          :placeholder="placeholder || '输入写作提示，Enter 发送，Shift+Enter 换行'"
          :disabled="streaming"
          type="textarea"
          :rows="3"
          resize="none"
          @keydown="onKeydown"
        />
        <div class="input-footer">
          <div class="footer-actions">
            <el-button class="selector-button" @click="emit('openKbSelector')">
              <span class="selector-button-label">{{ selectedKbLabel || '选择知识库' }}</span>
            </el-button>
          </div>
          <el-button
            class="send-button"
            :disabled="!inputText.trim() || streaming"
            @click="handleSend"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 2 11 13" />
              <path d="M22 2 15 22 11 13 2 9 22 2z" />
            </svg>
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ai-chat-inner {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 24px 0;
}

.messages-shell {
  width: min(720px, 80%);
}

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
}

.streaming-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.dot-pulse {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--el-color-primary);
  animation: pulse 1.2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}

.input-area {
  display: flex;
  justify-content: center;
  padding: 8px 0;
  background: var(--el-bg-color-overlay);
}

.input-shell {
  width: min(800px, 90%);
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
  justify-content: space-between;
  gap: 12px;
  margin-top: 8px;
}

.footer-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  min-width: 0;
}

.selector-button,
.send-button {
  height: 30px;
  padding: 0 10px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-light);
  border-color: transparent;
  border-radius: 999px;
}

.selector-button-label {
  display: inline-block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 320px;
}

.send-button {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
}
</style>
