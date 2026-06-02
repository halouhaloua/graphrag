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
}>();

const emit = defineEmits<{
  send: [question: string];
  convert: [content: string, msgId: string];
  openDocument: [doc: WriterDocument];
  deleteDocument: [docId: string];
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
        <ElInput
          v-model="inputText"
          :placeholder="placeholder || '输入写作提示，按 Enter 发送，Shift+Enter 换行'"
          :disabled="streaming"
          type="textarea"
          :rows="5"
          resize="none"
          @keydown="onKeydown"
        />
        <ElButton
          class="send-btn"
          type="primary"
          circle
          :disabled="!inputText.trim() || streaming"
          @click="handleSend"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 2 11 13" />
            <path d="M22 2 15 22 11 13 2 9 22 2z" />
          </svg>
        </ElButton>
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
  padding: 12px 16px;
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
  width: min(800px, 90%);
}

.input-shell {
  position: relative;
  width: min(800px, 90%);
}

.input-shell :deep(.el-textarea__inner) {
  padding-right: 44px;
  border-radius: 12px;
}

.send-btn {
  position: absolute;
  right: 8px;
  bottom: 8px;
  z-index: 1;
}
</style>
