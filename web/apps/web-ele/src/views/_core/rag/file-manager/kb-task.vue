<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Page } from '@vben/common-ui';
import { ElMessage, ElSkeleton, ElButton } from 'element-plus';
import { useAccessStore } from '@vben/stores';

import { RichTextEditor } from '#/components/zq-form/rich-text-editor';

import SidebarNav from './components/SidebarNav.vue';
import FilePreviewArea from './components/FilePreviewArea.vue';

import {
  getKbFileStreamUrl,
  getKbFileText,
  updateKbFileText,
} from './api/rag-file';
import { plainTextToHtml, htmlToPlainText } from './utils/file-utils';

defineOptions({ name: 'KbFileEditTask' });

const route = useRoute();
const router = useRouter();

const fileId = ref('');
const kbId = ref('');
const fileName = ref('');
const fileExt = ref('');
const streamUrl = ref('');
const loading = ref(true);
const saving = ref(false);
const saved = ref(false);

const textContent = ref('');

const sidebarCollapsed = ref(false);
const activeNav = ref<'preview' | 'edit' | 'split' | 'addToKb'>('edit');

onMounted(async () => {
  fileId.value = route.params.fileId as string;
  kbId.value = (route.query.kbId as string) || '';
  const accessToken = String(useAccessStore().accessToken);

  try {
    const textRes: any = await getKbFileText(fileId.value);
    fileName.value = textRes.filename || '';
    fileExt.value = (textRes.fileExt || '').toLowerCase().replace('.', '');
    textContent.value = plainTextToHtml(textRes.textContent || '');
    kbId.value = textRes.kbId || kbId.value;
    streamUrl.value = getKbFileStreamUrl(fileId.value, kbId.value, accessToken);
  } catch {
    ElMessage.error('加载文件失败');
  } finally {
    loading.value = false;
  }
});

async function handleSave() {
  saving.value = true;
  saved.value = false;
  try {
    const plain = htmlToPlainText(textContent.value);
    await updateKbFileText(fileId.value, plain);
    ElMessage.success('文本内容已保存');
    saved.value = true;
  } catch {
    ElMessage.error('保存失败');
  } finally {
    saving.value = false;
  }
}

function handleBack() {
  router.back();
}

function handleKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault();
    handleSave();
  }
}

onMounted(() => window.addEventListener('keydown', handleKeydown));
onBeforeUnmount(() => window.removeEventListener('keydown', handleKeydown));
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
            :ocr-status="'none'"
            :llm-status="'none'"
            :card="true"
          />

          <template v-if="activeNav === 'edit'">
            <div class="edit-wrapper">
              <RichTextEditor
                v-model="textContent"
                :max-height="99999"
                :show-word-count="true"
                :toolbar-config="{ groups: ['save', 'history', 'heading', 'format', 'color', 'align', 'list', 'insert', 'blockquote', 'code', 'divider', 'clear'] }"
                placeholder="暂无文本内容，请手动输入..."
                @save="handleSave"
              />
            </div>
          </template>

          <div v-if="activeNav === 'split'" class="split-view">
            <FilePreviewArea
              :file-ext="fileExt"
              :stream-url="streamUrl"
              :ocr-status="'none'"
              :llm-status="'none'"
              :card="false"
            />
            <div class="split-divider" />
            <div class="split-right">
              <RichTextEditor
                v-model="textContent"
                :max-height="99999"
                :show-word-count="false"
                :toolbar-config="{ groups: ['save', 'history', 'heading', 'format', 'color', 'align', 'list', 'insert', 'blockquote', 'code', 'divider', 'clear'] }"
                placeholder="暂无文本内容，请手动输入..."
                @save="handleSave"
              />
            </div>
          </div>

          <div v-if="activeNav === 'addToKb'" class="add-to-kb-info">
            <div class="info-card">
              <h3>知识库文件</h3>
              <p>该文件已在知识库中。如需管理知识库，请前往知识库管理页面。</p>
              <ElButton type="primary" @click="handleBack">返回文件列表</ElButton>
            </div>
          </div>
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

.add-to-kb-info {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
}

.info-card {
  text-align: center;
  padding: 40px;
  background: var(--el-bg-color-overlay);
  border-radius: 12px;
}

.info-card h3 {
  margin: 0 0 8px;
  font-size: 16px;
}

.info-card p {
  margin: 0 0 16px;
  color: var(--el-text-color-secondary);
}
</style>
