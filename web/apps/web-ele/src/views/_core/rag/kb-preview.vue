<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ArrowLeft, Download } from '@vben/icons';
import { $t } from '@vben/locales';
import { Page } from '@vben/common-ui';
import { ElButton, ElSkeleton } from 'element-plus';
import { useAccessStore } from '@vben/stores';

import { getKbFilePreviewUrl, getFileListApi } from '#/api/core/rag';
import FilePreviewContent from '#/components/FilePreviewContent.vue';

const route = useRoute();
const router = useRouter();

const kbId = ref('');
const fileId = ref('');
const fileName = ref('');
const fileExt = ref('');
const previewCustomUrl = ref('');
const loading = ref(true);

onMounted(async () => {
  kbId.value = route.params.kbId as string;
  fileId.value = route.params.fileId as string;
  const accessStore = useAccessStore();
  previewCustomUrl.value = getKbFilePreviewUrl(kbId.value, fileId.value, accessStore.accessToken);

  try {
    const res: any = await getFileListApi(kbId.value);
    const file = (res.items || []).find((f: any) => f.id === fileId.value);
    if (file) {
      fileName.value = file.filename || '';
      const idx = fileName.value.lastIndexOf('.');
      fileExt.value = idx > 0 ? fileName.value.slice(idx + 1) : (file.file_type || '');
    }
  } catch {
    fileName.value = '';
  } finally {
    loading.value = false;
  }
});

function goBack() {
  router.back();
}

function handleDownload() {
  const accessStore = useAccessStore();
  const token = accessStore.accessToken;
  const url = `${previewCustomUrl.value}?download=1&token=${token}`;
  window.open(url, '_blank');
}
</script>

<template>
  <Page auto-content-height>
    <div class="preview-page">
      <div class="preview-header">
        <ElButton text @click="goBack">
          <ArrowLeft class="size-4" />
          {{ $t('common.back') || '返回' }}
        </ElButton>
        <span class="preview-title">{{ fileName }}</span>
        <ElButton text type="primary" :icon="Download" @click="handleDownload">
          {{ $t('file-manager.download') }}
        </ElButton>
      </div>
      <div class="preview-content">
        <ElSkeleton v-if="loading" :rows="10" animated />
        <FilePreviewContent
          v-else
          :file-id="fileId"
          :file-name="fileName"
          :file-ext="fileExt"
          :custom-preview-url="previewCustomUrl"
        />
      </div>
    </div>
  </Page>
</template>

<style scoped>
.preview-page {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.preview-header {
  display: flex;
  align-items: center;
  gap: 12px;
  /* 1. 增大内边距，让header更舒展，不再“扁塌” */
  padding: 10px 16px;
  /* 2. 改为纯白色背景，和浅灰页面背景形成对比 */
  background: #ffffff;
  /* 3. 升级阴影，营造“悬浮感”，替代弱边框做分隔 */
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06), 0 1px 4px rgba(0, 0, 0, 0.04);
  /* 4. 去掉原有的淡边框，用阴影实现更柔和的分隔 */
  border-bottom: 1.4px solid #e4e7eb;
  flex-shrink: 0;
  /* 5. 可选：底部轻微圆角，让header和内容过渡更自然 */
  border-radius: 8px 8px 0 0;
  /* 6. 固定最小高度，保证视觉稳定性 */
  min-height: 50px;
}

/* 同时优化标题文字，提升可读性 */
.preview-title {
  flex: 1;
  font-size: 15px;
  font-weight: 500;
  color: #1d2129; /* 加深文字颜色，避免和浅背景融在一起 */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-content {
  flex: 1;
  overflow: hidden;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
</style>
