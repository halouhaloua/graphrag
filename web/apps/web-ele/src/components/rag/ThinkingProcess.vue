<script lang="ts" setup>
import { ref } from 'vue';
import { ElButton, ElTag } from 'element-plus';

defineOptions({ name: 'ThinkingProcess' });

const props = defineProps<{
  messageId: string;
  reasoningSteps?: any;
  subQuestions?: any[];
  retrievedTriples?: string[];
  retrievedChunks?: string[];
  expanded: boolean;
}>();

const emit = defineEmits<{
  'update:expanded': [value: boolean];
}>();

const triplesExpanded = ref<Set<string>>(new Set());
const chunksExpanded = ref<Set<string>>(new Set());
const CHUNK_PREVIEW_LENGTH = 40;

function toggleTriples(key: string) {
  if (triplesExpanded.value.has(key)) {
    triplesExpanded.value.delete(key);
  } else {
    triplesExpanded.value.add(key);
  }
}

function toggleChunks(key: string) {
  if (chunksExpanded.value.has(key)) {
    chunksExpanded.value.delete(key);
  } else {
    chunksExpanded.value.add(key);
  }
}

function toggleExpand() {
  emit('update:expanded', !props.expanded);
}
</script>

<template>
  <div class="thinking-section">
    <div class="thinking-header" @click="toggleExpand">
      <span class="thinking-icon">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2a10 10 0 0 1 10 10c0 2.5-1 4.8-2.5 6.5L20 22l-3.5-1.5A10 10 0 0 1 12 22 10 10 0 0 1 2 12 10 10 0 0 1 12 2z"/>
          <path d="M12 6v6l4 2"/>
        </svg>
      </span>
      <span class="thinking-label">
        检索完成
      </span>
      <span class="thinking-toggle" :class="{ collapsed: !expanded }">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
          <path d="m6 9 6 6 6-6"/>
        </svg>
      </span>
    </div>
    <div v-if="expanded" class="thinking-body">
      <div
        v-if="subQuestions && subQuestions.length > 0"
        class="metadata-summary"
      >
        <el-tag size="small" type="info">
          {{ subQuestions.length }} 子问题
        </el-tag>
        <el-tag size="small" type="warning">
          {{ retrievedTriples?.length || 0 }} 三元组
        </el-tag>
        <el-tag size="small" type="success">
          {{ retrievedChunks?.length || 0 }} 文本块
        </el-tag>
      </div>

      <template v-if="reasoningSteps">
        <div class="reasoning-section">
          <div
            v-for="(step, si) in reasoningSteps.reasoning_steps"
            :key="`step-${messageId}-${si}`"
            class="step-item"
          >
            <div class="step-question">
              <span class="step-icon">
                <svg
                  v-if="step.type === 'sub_question'"
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <circle cx="11" cy="11" r="8" />
                  <path d="m21 21-4.3-4.3" />
                </svg>
                <svg
                  v-else
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                  <path d="M21 3v5h-5" />
                </svg>
              </span>
              {{ step.question || step.type }}
            </div>

            <div
              v-if="step.triples && step.triples.length > 0"
              class="step-section"
            >
              <div class="step-section-title">三元组</div>
              <div
                v-for="(t, ti) in (triplesExpanded.has(`${messageId}-${si}`) ? step.triples : step.triples.slice(0, 2))"
                :key="ti"
                class="triple-item"
              >
                {{ t }}
              </div>
              <el-button
                v-if="step.triples.length > 2"
                class="toggle-inline-button"
                :class="{ expanded: triplesExpanded.has(`${messageId}-${si}`) }"
                size="small"
                @click="toggleTriples(`${messageId}-${si}`)"
              >
                {{ triplesExpanded.has(`${messageId}-${si}`) ? '收起' : '展开三元组' }}
              </el-button>
            </div>

            <div
              v-if="step.chunk_contents && step.chunk_contents.length > 0"
              class="step-section"
            >
              <div class="step-section-title">文本块</div>
              <template v-if="chunksExpanded.has(`${messageId}-${si}`)">
                <div
                  v-for="(ch, ci) in step.chunk_contents"
                  :key="ci"
                  class="chunk-item"
                >
                  {{ ch }}
                </div>
              </template>
              <template v-else>
                <div class="chunk-item-preview">
                  {{ step.chunk_contents[0].slice(0, CHUNK_PREVIEW_LENGTH) }}{{ step.chunk_contents[0].length > CHUNK_PREVIEW_LENGTH ? '...' : '' }}
                </div>
              </template>
              <el-button
                v-if="step.chunk_contents.length > 1 || (step.chunk_contents[0] && step.chunk_contents[0].length > CHUNK_PREVIEW_LENGTH)"
                class="toggle-inline-button"
                :class="{ expanded: chunksExpanded.has(`${messageId}-${si}`) }"
                size="small"
                @click="toggleChunks(`${messageId}-${si}`)"
              >
                {{ chunksExpanded.has(`${messageId}-${si}`) ? '收起' : '展开文本块' }}
              </el-button>
            </div>

            <div v-if="step.thought" class="step-section">
              <div class="step-section-title">推理</div>
              <div class="thought-text">{{ step.thought }}</div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.thinking-section {
  margin-bottom: 12px;
}

.thinking-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 0px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
  border-radius: 6px;
}

/* .thinking-header:hover {
  background: var(--el-fill-color-light);
} */

.thinking-icon {
  display: flex;
  align-items: center;
  color: var(--el-color-primary);
  flex-shrink: 0;
}

.thinking-label {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  min-width: 0;
}

.thinking-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-secondary);
  transition: transform 0.2s;
  flex-shrink: 0;
}

.thinking-toggle.collapsed {
  transform: rotate(-90deg);
}

.thinking-body {
  padding: 8px 0 8px 16px;
  border-left: 1.5px solid var(--el-border-color-lighter);
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.metadata-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.reasoning-section {
  margin-bottom: 0;
}

.step-item {
  margin-bottom: 16px;
}

.step-item:last-child {
  margin-bottom: 0;
}

.step-question {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 4px 0 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-regular);
}

.step-icon {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  color: var(--el-color-primary);
}

.step-section {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  margin-bottom: 8px;
}

.step-section-title {
  margin-bottom: 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  text-transform: uppercase;
}

.triple-item {
  width: 100%;
  padding: 6px 10px;
  margin-bottom: 4px;
  font-family: monospace;
  font-size: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}

.chunk-item {
  width: 100%;
  padding: 8px 10px;
  margin-bottom: 4px;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.5;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}

.chunk-item-preview {
  padding: 8px 10px;
  margin-bottom: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  line-height: 1.4;
  white-space: nowrap;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}

.thought-text {
  padding: 4px 6px;
  font-size: 11px;
  font-style: italic;
  background: var(--el-color-warning-light-9);
  border-radius: 4px;
}

button.toggle-inline-button {
  min-width: 104px;
  flex-shrink: 0;
  padding: 0 10px;
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 999px;
}

button.toggle-inline-button.expanded {
  max-width: 80%;
}

button.toggle-inline-button:hover {
  color: var(--el-text-color-regular);
  background: var(--el-fill-color);
}
</style>
