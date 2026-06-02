<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onErrorCaptured, ref, watch } from 'vue';
import { ElButton, ElInput } from 'element-plus';
import { PanelRight, Search } from '@vben/icons';

import VueOfficePdf from '@vue-office/pdf';
import VueOfficeDocx from '@vue-office/docx';

import type { PdfMatch } from '#/composables/usePdfSearch';

const props = defineProps<{
  fileExt: string;
  streamUrl: string;
  pdfPage: number;
  sidebarCollapsed: boolean;
  ocrStatus: string;
  llmStatus: string;
  card: boolean;
  searchVisible: boolean;
  searchQuery: string;
  searchMatches: PdfMatch[];
  searchMatchIndex: number;
  searchTotal: number;
}>();

const emit = defineEmits<{
  'update:pdfPage': [value: number];
  'toggle-sidebar': [];
  'toggle-search': [];
  ocr: [];
  'complex-ocr': [];
  'update:searchQuery': [value: string];
  search: [value: string];
  'search-prev': [];
  'search-next': [];
  'search-close': [];
  'go-to-search-match': [index: number];
}>();

const isPdf = computed(() => props.fileExt === 'pdf');
const isDocx = computed(() => props.fileExt === 'docx');

// @vue-office/pdf 在 beforeUnmount 时内部调用 r.destroy() 可能因 PDF 未完全加载而抛出
// "r.destroy is not a function"，捕获该错误阻止其传播到 Vue Router 导致导航中断
onErrorCaptured((err) => {
  if (String(err).includes('destroy is not a function')) {
    return false;
  }
});

const pdfContainerRef = ref<HTMLElement | null>(null);

const ZOOM_LEVELS = [0.5, 0.75, 1, 1.25, 1.5, 2];
const zoom = ref(1);
const pdfRef = ref<any>(null);

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

let scrollTimer: ReturnType<typeof setInterval> | null = null;

function scrollToPage(pageNum: number) {
  if (!isPdf.value) return;
  if (scrollTimer) { clearInterval(scrollTimer); scrollTimer = null; }

  nextTick(() => {
    let retries = 0;
    const maxRetries = 20;
    let scrolled = false;

    function tryScroll(): boolean {
      if (scrolled) return true;

      const container = pdfContainerRef.value;
      if (!container) {
        if (++retries < maxRetries) return false;
        cleanup();
        return false;
      }

      const target =
        container.querySelector<HTMLElement>(`[data-page-number="${pageNum}"]`)
        || container.querySelector<HTMLElement>(`[data-page="${pageNum}"]`)
        || container.querySelector<HTMLElement>(`#page-${pageNum}`)
        || container.querySelector<HTMLElement>(`.pageContainer-${pageNum}`)
        || container.querySelector<HTMLElement>(`.page:nth-of-type(${pageNum})`)
        || container.querySelector<HTMLElement>(`canvas:nth-of-type(${pageNum})`);

      if (target) {
        let scrollParent: HTMLElement | null = target.parentElement;
        while (scrollParent && scrollParent !== container && scrollParent !== document.body) {
          const style = window.getComputedStyle(scrollParent);
          if (style.overflowY === 'auto' || style.overflowY === 'scroll') break;
          scrollParent = scrollParent.parentElement;
        }
        const scroller = scrollParent && scrollParent !== document.body ? scrollParent : container;
        scroller.scrollTo({ top: target.offsetTop - target.offsetHeight - 20, behavior: 'smooth' });
        scrolled = true;
        cleanup();
        return true;
      }

      if (++retries >= maxRetries) { cleanup(); }
      return false;
    }

    function cleanup() {
      if (scrollTimer) { clearInterval(scrollTimer); scrollTimer = null; }
    }

    if (!tryScroll()) {
      scrollTimer = setInterval(tryScroll, 200);
    }
  });
}

onBeforeUnmount(() => {
  if (scrollTimer) {
    clearInterval(scrollTimer);
    scrollTimer = null;
  }
});

watch(() => props.pdfPage, scrollToPage);

function handleSearchKeydown(e: Event) {
  const ke = e as KeyboardEvent;
  if (ke.key === 'Enter') {
    ke.preventDefault();
    if (ke.shiftKey) {
      emit('search-prev');
    } else {
      emit('search-next');
    }
  }
  if (ke.key === 'Escape') {
    emit('search-close');
  }
}
</script>

<template>
  <div :class="card ? 'preview-card' : 'flat-wrapper'">
    <div class="action-bar">
      <template v-if="sidebarCollapsed">
        <ElButton
          :icon="PanelRight"
          circle
          size="small"
          @click="emit('toggle-sidebar')"
        />
      </template>
      <div class="action-buttons">
        <ElButton
          size="small"
          :icon="Search"
          text
          @click="emit('toggle-search')"
        />
        <ElButton
          size="small"
          :disabled="ocrStatus === 'pending'"
          text
          @click="emit('ocr')"
        >
          文字识别
        </ElButton>
        <ElButton
          size="small"
          text
          :disabled="!isPdf || llmStatus === 'pending'"
          @click="emit('complex-ocr')"
        >
          复杂竖排繁体文本OCR
        </ElButton>
      </div>
      <div class="zoom-controls">
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
      <div v-if="isPdf && searchVisible" class="search-bar">
        <ElInput
          :model-value="searchQuery"
          size="small"
          placeholder="在PDF中搜索..."
          clearable
          @input="emit('update:searchQuery', $event); emit('search', $event)"
          @keydown="handleSearchKeydown"
        />
        <span v-if="searchTotal > 0" class="search-count">
          {{ searchMatchIndex + 1 }}/{{ searchTotal }}
        </span>
        <ElButton size="small" text :disabled="searchMatchIndex <= 0" @click="emit('search-prev')">▲</ElButton>
        <ElButton size="small" text :disabled="searchMatchIndex >= searchTotal - 1" @click="emit('search-next')">▼</ElButton>
        <ElButton size="small" text @click="emit('search-close')">✕</ElButton>
      </div>
    </div>

    <div v-if="card" class="preview-body">
      <div v-if="isPdf" ref="pdfContainerRef" class="office-container">
        <VueOfficePdf ref="pdfRef" :page="pdfPage" :src="streamUrl" @update:page="emit('update:pdfPage', $event)" />
      </div>
      <div v-if="isDocx" class="office-container" :style="isDocx ? { zoom } : undefined">
        <VueOfficeDocx :src="streamUrl" />
      </div>
      <div v-if="!isPdf && !isDocx" class="unsupported-tip">
        暂不支持预览该文件类型
      </div>
    </div>
    <template v-else>
      <div v-if="isPdf" ref="pdfContainerRef" class="office-container">
        <VueOfficePdf ref="pdfRef" :page="pdfPage" :src="streamUrl" @update:page="emit('update:pdfPage', $event)" />
      </div>
      <div v-if="isDocx" class="office-container" :style="isDocx ? { zoom } : undefined">
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
  gap: 12px;
  padding: 10px 16px;
  background: #ffffff;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  border-bottom: 1px solid #e4e7eb;
  z-index: 10;
  min-height: 46px;
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

.search-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.search-bar :deep(.el-input) {
  width: 180px;
}

.search-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  min-width: 50px;
  text-align: center;
}

</style>
