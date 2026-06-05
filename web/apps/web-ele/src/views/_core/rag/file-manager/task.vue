<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue';
import { useRoute } from 'vue-router';
import { Page } from '@vben/common-ui';
import { ElMessage, ElMessageBox, ElSkeleton } from 'element-plus';
import { useAccessStore } from '@vben/stores';

import { RichTextEditor } from '#/components/zq-form/rich-text-editor';

import SidebarNav from './components/SidebarNav.vue';
import FilePreviewArea from './components/FilePreviewArea.vue';
import KbSelectTable from './components/KbSelectTable.vue';

import {
  estimateComplexOcr,
  getFileStreamUrl,
  getFileText,
  addFileToKb,
  triggerOcr,
  triggerComplexOcr,
  getKbListForSelect,
  getRagFileInfo,
  updateFileText,
} from './api/rag-file';
import { plainTextToHtml, htmlToPlainText } from './utils/file-utils';

defineOptions({ name: 'RagFileTask' });

const route = useRoute();

const fileId = ref('');
const fileName = ref('');
const fileExt = ref('');
const streamUrl = ref('');
const loading = ref(true);

const textContent = ref('');
const ocrStatus = ref('none');
const llmStatus = ref('none');

const sidebarCollapsed = ref(false);
const activeNav = ref<'preview' | 'edit' | 'split' | 'addToKb'>('preview');
const saving = ref(false);

const kbList = ref<Array<{ id: string; name: string; description?: string }>>([]);
const addingToKb = ref(false);
const kbPage = ref(1);
const kbPageSize = ref(10);
const kbTotal = ref(0);
const loadingKb = ref(false);

const accessToken = String(useAccessStore().accessToken);

onMounted(async () => {
  fileId.value = route.params.fileId as string;

  try {
    const file: any = await getRagFileInfo(fileId.value);
    fileName.value = file.name || '';
    fileExt.value = (file.fileExt || '').toLowerCase().replace('.', '');
  } catch {
    fileName.value = '';
  }

  try {
    const textRes: any = await getFileText(fileId.value);
    textContent.value = plainTextToHtml(textRes.textContent || '');
    ocrStatus.value = textRes.ocrStatus || 'none';
    llmStatus.value = textRes.llmStatus || 'none';
  } catch {
    textContent.value = '';
  }

  streamUrl.value = getFileStreamUrl(fileId.value, accessToken);

  await fetchKbList();

  loading.value = false;
});

async function handleSave() {
  saving.value = true;
  try {
    const plain = htmlToPlainText(textContent.value);
    await updateFileText(fileId.value, plain);
    ElMessage.success('文本内容已保存');
  } catch {
    ElMessage.error('保存失败');
  } finally {
    saving.value = false;
  }
}

function handleKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault();
    handleSave();
  }
}

onMounted(() => window.addEventListener('keydown', handleKeydown));
onBeforeUnmount(() => window.removeEventListener('keydown', handleKeydown));

async function fetchKbList() {
  loadingKb.value = true;
  try {
    const kbRes: any = await getKbListForSelect(kbPage.value, kbPageSize.value);
    kbList.value = (kbRes.items || []).map((kb: any) => ({
      id: kb.id,
      name: kb.name,
      description: kb.description || '',
    }));
    kbTotal.value = kbRes.total || 0;
  } catch {
    kbList.value = [];
  } finally {
    loadingKb.value = false;
  }
}

async function handleAddToKb(kbId: string) {
  addingToKb.value = true;
  try {
    await addFileToKb(fileId.value, kbId);
    ElMessage.success('已添加到知识库');
  } catch (err: any) {
    ElMessage.error(err.message || '添加到知识库失败');
  } finally {
    addingToKb.value = false;
  }
}

function handleKbPageChange(page: number) {
  kbPage.value = page;
  fetchKbList();
}

function handleKbSizeChange(size: number) {
  kbPageSize.value = size;
  kbPage.value = 1;
  fetchKbList();
}

async function handleOcr() {
  try {
    await triggerOcr(fileId.value);
    const textRes: any = await getFileText(fileId.value);
    textContent.value = plainTextToHtml(textRes.textContent || '');
    ocrStatus.value = textRes.ocrStatus || 'none';
    ElMessage.success('传统OCR识别完成');
    activeNav.value = 'edit';
  } catch {
    ElMessage.info('传统OCR识别失败');
  }
}

async function handleComplexOcr() {
  try {
    const est: any = await estimateComplexOcr(fileId.value);
    try {
      await ElMessageBox.confirm(
        `PDF 共 ${est.totalPages} 页，当前使用 ${est.device}，预计需约 ${est.estimatedMinutes} 分钟。\n\n是否继续识别？`,
        '确认识别',
        { confirmButtonText: '开始识别', cancelButtonText: '取消', type: 'info' },
      )
    } catch {
      return
    }
  } catch {
    // 预估失败，直接执行
  }
  try {
    await triggerComplexOcr(fileId.value);
    const textRes: any = await getFileText(fileId.value);
    textContent.value = plainTextToHtml(textRes.textContent || '');
    llmStatus.value = textRes.llmStatus || 'none';
    ElMessage.success('复杂竖排繁体文本OCR完成');
    activeNav.value = 'edit';
  } catch {
    ElMessage.info('复杂竖排繁体文本OCR识别失败');
  }
}
</script>

<template>
  <Page auto-content-height>
    <div class="task-page">
      <SidebarNav
        :collapsed="sidebarCollapsed"
        :active-nav="activeNav"
        @update:collapsed="sidebarCollapsed = $event"
        @update:active-nav="activeNav = $event"
      />

      <div class="main-area">
        <ElSkeleton v-if="loading" :rows="15" animated />

        <template v-else>
          <FilePreviewArea
            v-if="activeNav === 'preview'"
            :file-ext="fileExt"
            :stream-url="streamUrl"
            :ocr-status="ocrStatus"
            :llm-status="llmStatus"
            :sidebar-collapsed="sidebarCollapsed"
            :card="true"
            @ocr="handleOcr"
            @complex-ocr="handleComplexOcr"
            @expand-sidebar="sidebarCollapsed = false"
          />

          <template v-if="activeNav === 'edit'">
            <div class="edit-wrapper">
              <RichTextEditor
                v-model="textContent"
                :max-height="99999"
                :show-word-count="true"
                :sidebar-collapsed="sidebarCollapsed"
                :toolbar-config="{ groups: ['save', 'history', 'heading', 'format', 'color', 'align', 'list', 'insert', 'blockquote', 'code', 'divider', 'clear'] }"
                placeholder="暂无文本内容，请手动输入或使用识别功能提取文字..."
                @save="handleSave"
                @expand-sidebar="sidebarCollapsed = false"
              />
            </div>
          </template>

          <div v-if="activeNav === 'split'" class="split-view">
            <FilePreviewArea
              :file-ext="fileExt"
              :stream-url="streamUrl"
              :ocr-status="ocrStatus"
              :llm-status="llmStatus"
              :sidebar-collapsed="sidebarCollapsed"
              :card="false"
              @ocr="handleOcr"
              @complex-ocr="handleComplexOcr"
              @expand-sidebar="sidebarCollapsed = false"
            />
            <div class="split-divider" />
            <div class="split-right">
              <RichTextEditor
                v-model="textContent"
                :max-height="99999"
                :show-word-count="false"
                :toolbar-config="{ groups: ['save', 'history', 'heading', 'format', 'color', 'align', 'list', 'insert', 'blockquote', 'code', 'divider', 'clear'] }"
                placeholder="暂无文本内容，请手动输入或使用识别功能提取文字..."
                @save="handleSave"
              />
            </div>
          </div>

          <KbSelectTable
            v-if="activeNav === 'addToKb'"
            :kb-list="kbList"
            :loading="loadingKb"
            :adding-to-kb="addingToKb"
            :page="kbPage"
            :page-size="kbPageSize"
            :total="kbTotal"
            @add="handleAddToKb"
            @update:page="handleKbPageChange"
            @update:page-size="handleKbSizeChange"
          />
        </template>
      </div>
    </div>
  </Page>
</template>

<style scoped>
.task-page {
  display: flex;
  gap: 12px;
  height: 100%;
}

.main-area {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.edit-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.edit-wrapper :deep(.rich-text-editor) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  border-radius: 12px;
  overflow: hidden;
}

.edit-wrapper :deep(.editor-content) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.edit-wrapper :deep(.tiptap) {
  max-width: 820px;
  margin: 0 auto;
  padding: 24px 32px;
  line-height: 1.8;
  font-size: 14px;
}

.split-view {
  display: flex;
  flex: 1;
  min-height: 0;
}

.split-divider {
  width: 1px;
  background: var(--el-border-color-lighter);
  flex-shrink: 0;
}

.split-right {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.split-right :deep(.rich-text-editor) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

.split-right :deep(.editor-content) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.split-right :deep(.tiptap) {
  max-width: 100%;
  margin: 0;
  padding: 16px 20px;
  line-height: 1.8;
  font-size: 14px;
}
</style>
