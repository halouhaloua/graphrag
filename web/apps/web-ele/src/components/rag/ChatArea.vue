<script lang="ts" setup>
import type { ChatMessageItem } from '#/composables/useChat';

import { computed, nextTick, ref, watch } from 'vue';

import { ElButton, ElInput } from 'element-plus';
import { marked } from 'marked';
import ThinkingProcess from '#/components/rag/ThinkingProcess.vue';

const props = defineProps<{
  kbFileLabel?: string;
  ircotEnabled?: boolean;
  loading?: boolean;
  messages: ChatMessageItem[];
  placeholder?: string;
  streaming?: boolean;
}>();

const emit = defineEmits<{
  ircotToggle: [enabled: boolean];
  openSelector: [];
  send: [question: string];
}>();

const inputText = ref('');
const messagesContainer = ref<HTMLElement | null>(null);
const thinkingCollapsed = ref<Set<string>>(new Set());

function toggleThinkingCollapsed(id: string) {
  if (thinkingCollapsed.value.has(id)) {
    thinkingCollapsed.value.delete(id);
  } else {
    thinkingCollapsed.value.add(id);
  }
}

function isThinkingExpanded(id: string): boolean {
  return !thinkingCollapsed.value.has(id);
}

function hasReasoning(msg: ChatMessageItem): boolean {
  return !!(msg.reasoningSteps || msg.subQuestions?.length || msg.retrievedTriples?.length || msg.retrievedChunks?.length);
}

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

function renderMarkdown(content: string): string {
  if (!content) return '';
  return marked.parse(content, { breaks: true }) as string;
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    if (!e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }
}

const scrollKey = computed(() => {
  const len = props.messages.length;
  if (len === 0) return 0;
  return len + '-' + (props.messages[len - 1]?.content?.length ?? 0);
});

watch(scrollKey, () => { nextTick(scrollToBottom); }, { flush: 'post' });
</script>

<template>
  <div class="chat-area">
    <div ref="messagesContainer" class="messages-container">
      <div v-if="messages.length === 0" class="empty-state">
        <div class="empty-icon">
          <svg
            width="48"
            height="48"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
          >
            <path
              d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"
            />
          </svg>
        </div>
        <p>输入问题开始对话</p>
        <div class="quick-questions">
          <el-button
            size="small"
            @click="emit('send', '这个文件的主要内容是什么？')"
          >
            文件内容概述
          </el-button>
          <el-button
            size="small"
            @click="emit('send', '提取文件中的关键实体和关系')"
          >
            提取实体关系
          </el-button>
          <el-button size="small" @click="emit('send', '总结文件的核心观点')">
            核心观点总结
          </el-button>
        </div>
      </div>
      <div
        v-for="msg in messages"
        :key="msg.id"
        class="message-row"
        :class="msg.role"
      >
        <template v-if="msg.role === 'user'">
          <div class="message-content">
            <div class="bubble user-bubble">
              <div class="text">{{ msg.content }}</div>
            </div>
          </div>
        </template>
        <template v-else>
          <div class="message-content">
            <ThinkingProcess
              v-if="hasReasoning(msg)"
              :message-id="msg.id"
              :reasoning-steps="msg.reasoningSteps"
              :sub-questions="msg.subQuestions"
              :retrieved-triples="msg.retrievedTriples"
              :retrieved-chunks="msg.retrievedChunks"
              :thinking-time="msg.thinkingTime"
              :expanded="isThinkingExpanded(msg.id)"
              @update:expanded="toggleThinkingCollapsed(msg.id)"
            />
            <!-- Final Answer Section -->
            <div class="answer-section">
              <div class="md-content" v-html="renderMarkdown(msg.content)"></div>
            </div>
          </div>
        </template>
      </div>
      <div v-if="streaming" class="streaming-indicator">
        <span class="dot-pulse"></span>
        <span>AI 正在思考...</span>
      </div>
    </div>

    <div class="input-area">
      <div class="input-shell">
        <el-input
          v-model="inputText"
          :placeholder="placeholder || '输入您的问题，Enter 发送，Shift+Enter 换行'"
          :disabled="streaming"
          type="textarea"
          :rows="3"
          resize="none"
          @keydown="onKeydown"
        />
        <div class="input-footer">
          <div class="footer-actions">
            <el-button class="selector-button" @click="emit('openSelector')">
              <span class="selector-button-label">{{ kbFileLabel || '选择知识库 / 文件' }}</span>
            </el-button>
            <el-button
              v-if="ircotEnabled !== undefined"
              class="mode-button"
              :class="{ active: ircotEnabled }"
              @click="emit('ircotToggle', !ircotEnabled)"
            >
              IRCoT
            </el-button>
          </div>
          <el-button
            type="primary"
            circle
            class="send-button"
            :disabled="!inputText.trim()"
            @click="handleSend"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
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
.chat-area {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--el-bg-color);
}

.messages-container {
  flex: 1;
  padding: 16px 0;
  overflow-y: auto;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--el-text-color-secondary);
}

.quick-questions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-top: 16px;
}

.empty-icon {
  margin-bottom: 12px;
  font-size: 48px;
}

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

.answer-section {
  padding: 0;
}

.streaming-indicator {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 12px 0 8px 0;
  margin-left: auto;
  margin-right: auto;
  width: min(800px, 80%);
  font-size: 13px;
  color: var(--el-text-color-secondary);
  padding-left: 16px;
}

.dot-pulse {
  width: 8px;
  height: 8px;
  background: var(--el-color-primary);
  border-radius: 50%;
  animation: pulse 1.2s infinite;
  flex-shrink: 0;
  position: relative;
  top: -1px;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 0.4;
    transform: scale(1);
  }
  50% {
    opacity: 1;
    transform: scale(1.2);
  }
}

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
.mode-button {
  height: 36px;
  padding: 0 14px;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-light);
  border-color: transparent;
  border-radius: 999px;
}

.selector-button {
  max-width: 320px;
}

.selector-button-label {
  display: inline-block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mode-button.active {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-7);
}

.send-button {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
}

.selector-button,
.mode-button {
  height: 30px;
  padding: 0 10px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-light);
  border-color: transparent;
  border-radius: 999px;
}

@media (max-width: 768px) {
  .input-footer {
    align-items: stretch;
  }

  .footer-actions {
    flex: 1;
  }

  .selector-button {
    max-width: none;
    flex: 1;
  }
}
</style>
