<script setup lang="ts">
import { computed, onErrorCaptured, ref } from 'vue';
import { ElButton } from 'element-plus';
import { PanelRight } from '@vben/icons';

import VueOfficePdf from '@vue-office/pdf';
import VueOfficeDocx from '@vue-office/docx';

const props = defineProps<{
  fileExt: string;
  streamUrl: string;
  ocrStatus: string;
  llmStatus: string;
  card: boolean;
  sidebarCollapsed?: boolean;
}>();

defineEmits<{
  ocr: [];
  'complex-ocr': [];
  expandSidebar: [];
}>();

const isPdf = computed(() => props.fileExt === 'pdf');
const isDocx = computed(() => props.fileExt === 'docx');

const pdfRef = ref<any>(null);
const ZOOM_LEVELS = [0.5, 0.75, 1, 1.25, 1.5, 2];
const zoom = ref(1);

function zoomIn() {
  const idx = ZOOM_LEVELS.indexOf(zoom.value);
  if (idx < ZOOM_LEVELS.length - 1) {
    zoom.value = ZOOM_LEVELS[idx + 1]!;
    applyZoom();
  }
}

function zoomOut() {
  const idx = ZOOM_LEVELS.indexOf(zoom.value);
  if (idx > 0) {
    zoom.value = ZOOM_LEVELS[idx - 1]!;
    applyZoom();
  }
}

function applyZoom() {
  if (isPdf.value && pdfRef.value?.setScale) {
    pdfRef.value.setScale(zoom.value);
  }
}

onErrorCaptured((err) => {
  if (String(err).includes('destroy is not a function')) {
    return false;
  }
});
</script>

<template>
  <div :class="card ? 'preview-card' : 'flat-wrapper'">
    <div class="action-bar">
      <ElButton
        v-if="sidebarCollapsed"
        :icon="PanelRight"
        circle
        size="small"
        class="sidebar-expand-btn"
        @click="$emit('expandSidebar')"
      />
      <div class="action-buttons">
        <ElButton
          size="small"
          :disabled="ocrStatus === 'pending'"
          text
          @click="$emit('ocr')"
        >
          文字识别
        </ElButton>
        <ElButton
          size="small"
          text
          :disabled="!isPdf || llmStatus === 'pending'"
          @click="$emit('complex-ocr')"
        >
          复杂竖排繁体文本OCR
        </ElButton>
      </div>
      <div v-if="isPdf" class="zoom-controls">
        <ElButton
          size="small"
          text
          :disabled="zoom <= ZOOM_LEVELS[0]!"
          @click="zoomOut"
        >
          −
        </ElButton>
        <span class="zoom-level">{{ Math.round(zoom * 100) }}%</span>
        <ElButton
          size="small"
          text
          :disabled="zoom >= ZOOM_LEVELS[ZOOM_LEVELS.length - 1]!"
          @click="zoomIn"
        >
          +
        </ElButton>
      </div>
    </div>

    <div v-if="card" class="preview-body">
      <div v-if="isPdf && streamUrl" class="office-container">
        <VueOfficePdf ref="pdfRef" :src="streamUrl" />
      </div>
      <div v-if="isDocx && streamUrl" class="office-container" :style="{ zoom }">
        <VueOfficeDocx :src="streamUrl" />
      </div>
      <div v-if="!isPdf && !isDocx" class="unsupported-tip">
        暂不支持预览该文件类型
      </div>
    </div>
    <template v-else>
      <div v-if="isPdf && streamUrl" class="office-container">
        <VueOfficePdf ref="pdfRef" :src="streamUrl" />
      </div>
      <div v-if="isDocx && streamUrl" class="office-container" :style="{ zoom }">
        <VueOfficeDocx :src="streamUrl" />
      </div>
      <div v-if="!isPdf && !isDocx" class="unsupported-tip">
        暂不支持预览该文件类型
      </div>
    </template>
  </div>
</template>

<style scoped>
.preview-card {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  border-radius: 12px 12px 0 0;
  border: 1px solid #e4e7eb;
  overflow: hidden;
  background: #ffffff;
}

.flat-wrapper {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  border: 1px solid #e4e7eb;
  background: #ffffff;
  border-radius: 4px;
}

.action-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: #ffffff;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  border-bottom: 1px solid #e4e7eb;
  z-index: 10;
  min-height: 46px;
}

.sidebar-expand-btn {
  flex-shrink: 0;
}

.action-buttons {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.zoom-controls {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-left: auto;
}

.zoom-level {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  min-width: 36px;
  text-align: center;
  user-select: none;
}

.preview-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.office-container {
  height: 100%;
  overflow-y: auto;
}

.office-container > :deep(*) {
  width: 100%;
  height: 100%;
  border: none;
}

.unsupported-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--el-text-color-secondary);
}
</style>
