<script lang="ts" setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { ElButton, ElMessage } from 'element-plus';
import { Copy, FileTextOutlined } from '@vben/icons';
import { marked } from 'marked';
import WriterDocumentCard from '#/components/rag/WriterDocumentCard.vue';
import type { WriterDocument } from '#/api/core/rag';

export interface AiMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
}

const props = defineProps<{
  message: AiMessage;
  documentsByMsgId?: Record<string, WriterDocument[]>;
}>();

const emit = defineEmits<{
  convert: [content: string, msgId: string];
  openDocument: [doc: WriterDocument];
  deleteDocument: [docId: string];
}>();

const displayContent = ref(props.message.content);
let throttleTimer: ReturnType<typeof setTimeout> | null = null;
const THROTTLE_MS = 40;

function flushThrottled() {
  throttleTimer = null;
  displayContent.value = props.message.content;
  if (props.message.streaming) {
    throttleTimer = setTimeout(flushThrottled, THROTTLE_MS);
  }
}

watch(
  () => props.message.content,
  (val) => {
    if (props.message.streaming) {
      if (!throttleTimer) {
        displayContent.value = val;
        throttleTimer = setTimeout(flushThrottled, THROTTLE_MS);
      }
    } else {
      if (throttleTimer) clearTimeout(throttleTimer);
      throttleTimer = null;
      displayContent.value = val;
    }
  },
);

onBeforeUnmount(() => {
  if (throttleTimer) clearTimeout(throttleTimer);
});

const renderedHTML = computed(() => {
  if (!displayContent.value) return '';
  return marked.parse(displayContent.value, { breaks: true }) as string;
});

function copyContent(content: string) {
  navigator.clipboard.writeText(content).then(
    () => ElMessage.success('已复制'),
    () => ElMessage.error('复制失败'),
  );
}
</script>

<template>
  <div class="message-row" :class="message.role">
    <template v-if="message.role === 'user'">
      <div class="bubble user-bubble">
        <div class="text">{{ message.content }}</div>
      </div>
    </template>
    <template v-else>
      <div class="assistant-content">
        <div class="md-content" v-html="renderedHTML"></div>
        <div
          v-if="message.role === 'assistant' && !message.streaming"
          class="assistant-actions"
        >
          <ElButton
            size="small"
            :icon="FileTextOutlined"
            @click="emit('convert', message.content, message.id)"
            text
          >
            转为文档编辑
          </ElButton>
          <ElButton
            size="small"
            :icon="Copy"
            @click="copyContent(message.content)"
            text
          >
            复制
          </ElButton>
        </div>
        <div
          v-if="documentsByMsgId?.[message.id]?.length"
          class="document-cards"
        >
          <WriterDocumentCard
            v-for="doc in documentsByMsgId![message.id]"
            :key="doc.id"
            :document="doc"
            @open="emit('openDocument', $event)"
            @delete="emit('deleteDocument', $event)"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.message-row {
  display: flex;
  margin-bottom: 20px;
}

.message-row.user {
  justify-content: flex-end;
}

.message-row.assistant {
  justify-content: flex-start;
}

.bubble {
  max-width: 75%;
  padding: 10px 16px;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.6;
  word-wrap: break-word;
}

.user-bubble {
  position: relative;
  background: var(--el-color-primary-light-8);
  color: var(--el-text-color-primary);
}

.assistant-content {
  position: relative;
  max-width: 85%;
}

.assistant-actions {
  display: flex;
  margin-top: 8px;
  padding-left: 6px;
}

.assistant-actions :deep(.el-button.is-text) {
  color: #888a91;
}

.assistant-actions :deep(.el-button.is-text:hover) {
  color: #606266;
  background: var(--el-fill-color-light);
}

.document-cards {
  padding-left: 16px;
}

.md-content {
  font-size: 15px;
  line-height: 1.75;
  word-wrap: break-word;
  margin-left: 16px;
  color: var(--el-text-color-primary);
}

.md-content :deep(p) {
  margin: 0 0 1.25em;
}

.md-content :deep(p:last-child) {
  margin-bottom: 0;
}

.md-content :deep(h1),
.md-content :deep(h2),
.md-content :deep(h3),
.md-content :deep(h4) {
  margin: 1.5em 0 0.5em;
  font-weight: 600;
  line-height: 1.3;
}

.md-content :deep(h1) { font-size: 1.5em; }
.md-content :deep(h2) { font-size: 1.25em; }
.md-content :deep(h3) { font-size: 1.1em; }
.md-content :deep(h4) { font-size: 1em; }

.md-content :deep(h1:first-child),
.md-content :deep(h2:first-child),
.md-content :deep(h3:first-child) {
  margin-top: 0;
}

.md-content :deep(ul),
.md-content :deep(ol) {
  padding-left: 1.5em;
  margin: 0.5em 0 1em;
}

.md-content :deep(li) {
  margin-bottom: 0.25em;
}

.md-content :deep(li:last-child) {
  margin-bottom: 0;
}

.md-content :deep(blockquote) {
  margin: 0.75em 0;
  padding: 0.5em 1em;
  border-left: 3px solid var(--el-color-primary);
  background: var(--el-fill-color-lighter);
  border-radius: 0 6px 6px 0;
  color: var(--el-text-color-secondary);
}

.md-content :deep(pre) {
  background: var(--el-fill-color);
  padding: 14px 16px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 0.9em;
  line-height: 1.6;
  margin: 0.75em 0;
}

.md-content :deep(code) {
  font-size: 0.9em;
  background: var(--el-fill-color-light);
  padding: 0.2em 0.4em;
  border-radius: 4px;
}

.md-content :deep(pre code) {
  background: transparent;
  padding: 0;
}

.md-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 1em 0;
  font-size: 0.9em;
}

.md-content :deep(th),
.md-content :deep(td) {
  padding: 10px 14px;
  border: 1px solid var(--el-border-color-light);
  text-align: left;
}

.md-content :deep(th) {
  background: var(--el-fill-color-light);
  font-weight: 600;
}

.md-content :deep(tr:nth-child(even)) {
  background: var(--el-fill-color-lighter);
}

.md-content :deep(hr) {
  margin: 1.5em 0;
  border: none;
  border-top: 1px solid var(--el-border-color-light);
}
</style>
