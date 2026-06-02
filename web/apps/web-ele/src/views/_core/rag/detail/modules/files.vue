<script lang="ts" setup>
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { ElButton, ElMessage, ElMessageBox, ElTag, ElTable, ElTableColumn, ElDialog, ElProgress, ElUpload } from 'element-plus';
import { Eye, RefreshCw, Plus, Trash2, Upload } from '@vben/icons';
import type { KnowledgeBaseFile } from '#/api/core/rag';
import {
  getFileListApi,
  deleteFileApi,
  reconstructGraphApi,
  getKbFileContentApi,
  mergeKbGraphsApi,
  incrementalFileUpdateApi,
} from '#/api/core/rag';
import { useGraphProgress } from '#/composables/useGraphProgress';

import UploadDialog from './upload-dialog.vue';
import SchemaEditor from './schema-editor.vue';

const props = defineProps<{ kbId: string }>();
const emit = defineEmits<{ navigateGraph: [fileId: string] }>();

const files = ref<KnowledgeBaseFile[]>([]);
const loading = ref(false);
const constructingId = ref<string | null>(null);
const progressMessage = ref('');
const uploadDialogRef = ref<InstanceType<typeof UploadDialog>>();
const schemaEditorRef = ref<InstanceType<typeof SchemaEditor>>();
const contentDialogVisible = ref(false);
const contentText = ref('');
const contentFilename = ref('');
const contentLoading = ref(false);
const incrementalDialogVisible = ref(false);
const incrementalTargetFile = ref<KnowledgeBaseFile | null>(null);
const incrementalUploading = ref(false);

const { showProgressDialog, progress, constructWithProgress } = useGraphProgress();

async function loadFiles() {
  loading.value = true;
  try {
    const res = await getFileListApi(props.kbId);
    files.value = res.items;
  } catch (err: any) {
    ElMessage.error(err.message || '加载文件列表失败');
  } finally {
    loading.value = false;
  }
}

async function handleMerge() {
  try {
    await mergeKbGraphsApi(props.kbId);
    ElMessage.success('图谱合并完成');
    loadFiles();
  } catch (err: any) {
    ElMessage.error('合并图谱失败: ' + (err.message || ''));
  }
}

async function handleMergeAll() {
  try {
    await mergeKbGraphsApi(props.kbId);
    ElMessage.success('图谱合并完成');
    loadFiles();
  } catch (err: any) {
    ElMessage.error('合并图谱失败: ' + (err.message || ''));
  }
}

function isMergedFile(file: KnowledgeBaseFile) {
  return file.file_type === 'merged';
}

function openIncrementalDialog(file: KnowledgeBaseFile) {
  incrementalTargetFile.value = file;
  incrementalDialogVisible.value = true;
}

async function handleIncrementalUpload(uploadFile: any) {
  const fileObj = uploadFile.raw || uploadFile.file;
  if (!fileObj || !incrementalTargetFile.value) return;
  incrementalUploading.value = true;
  try {
    await incrementalFileUpdateApi(props.kbId, incrementalTargetFile.value.id, fileObj);
    ElMessage.success('增量更新完成');
    incrementalDialogVisible.value = false;
    loadFiles();
  } catch (err: any) {
    ElMessage.error('增量更新失败: ' + (err.message || ''));
  } finally {
    incrementalUploading.value = false;
  }
}

async function handleDelete(file: KnowledgeBaseFile) {
  if (isMergedFile(file)) {
    ElMessage.warning('不能删除合并图谱');
    return;
  }
  try {
    await ElMessageBox.confirm(
      `确定删除文件「${file.filename}」？图谱数据将一并删除。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    );
    await deleteFileApi(props.kbId, file.id);
    ElMessage.success('删除成功');
    loadFiles();
  } catch {
    // cancelled
  }
}

async function handleConstructGraph(file: KnowledgeBaseFile) {
  constructingId.value = file.id;

  try {
    if (file.has_graph) {
      await reconstructGraphApi(props.kbId, file.id);
      ElMessage.success('图谱重建成功');
    } else {
      await constructWithProgress(
        props.kbId,
        file.id,
        (msg, _pct) => { progressMessage.value = msg; },
      );
      ElMessage.success('图谱构建成功');
    }
    loadFiles();
  } catch (err: any) {
    ElMessage.error(err.message || '构建失败');
  } finally {
    constructingId.value = null;
    progressMessage.value = '';
  }
}

function handleUploadComplete() {
  loadFiles();
}

function handleEditSchema(file: KnowledgeBaseFile) {
  schemaEditorRef.value?.open(file);
}

const router = useRouter();

function handlePreview(file: KnowledgeBaseFile) {
  router.push(`/rag/knowledge-base/${props.kbId}/files/${file.id}/preview`);
}

async function handleViewContent(file: KnowledgeBaseFile) {
  contentLoading.value = true;
  contentDialogVisible.value = true;
  contentText.value = '';
  contentFilename.value = file.filename;
  try {
    const res = await getKbFileContentApi(props.kbId, file.id);
    contentText.value = res.content;
  } catch (err: any) {
    contentText.value = '加载文本内容失败: ' + (err.message || '');
  } finally {
    contentLoading.value = false;
  }
}

onMounted(() => {
  loadFiles();
});
</script>

<template>
  <div class="files-tab">
    <div class="tab-toolbar">
      <ElButton type="primary" :icon="Plus" @click="uploadDialogRef?.open()">
        上传文件
      </ElButton>
      <ElButton :icon="RefreshCw" @click="handleMergeAll" style="margin-left: 8px">
        合并所有图谱
      </ElButton>
    </div>

    <ElTable :data="files" v-loading="loading" stripe border style="width: 100%">
      <ElTableColumn prop="filename" label="文件名" min-width="160">
        <template #default="{ row }">
          <span v-if="isMergedFile(row)" class="merged-label"> {{ row.filename }}</span>
          <span v-else>{{ row.filename }}</span>
        </template>
      </ElTableColumn>
      <ElTableColumn prop="file_type" label="类型" width="80" />
      <ElTableColumn prop="file_size" label="大小" width="80">
        <template #default="{ row }">
          <template v-if="isMergedFile(row)">—</template>
          <template v-else-if="row.file_size < 1048576">
            {{ (row.file_size / 1024).toFixed(1) }} KB
          </template>
          <template v-else>
            {{ (row.file_size / 1048576).toFixed(1) }} MB
          </template>
        </template>
      </ElTableColumn>
      <ElTableColumn label="图谱状态" width="100">
        <template #default="{ row }">
          <ElTag v-if="isMergedFile(row)" type="warning" size="small">已合并</ElTag>
          <ElTag v-else :type="row.has_graph ? 'success' : 'info'" size="small">
            {{ row.has_graph ? '已构建' : '未构建' }}
          </ElTag>
        </template>
      </ElTableColumn>
      <ElTableColumn label="操作" width="500" fixed="right">
        <template #default="{ row }">
          <template v-if="isMergedFile(row)">
            <ElButton link type="primary" :icon="RefreshCw" @click="handleMerge">
              合并
            </ElButton>
            <ElButton link type="primary" :icon="Eye" @click="emit('navigateGraph', row.id)">
              查看图谱
            </ElButton>
          </template>
          <template v-else>
            <ElButton link type="primary" @click="handlePreview(row)">
              预览
            </ElButton>
            <ElButton link type="primary" @click="handleViewContent(row)">
              查看文本
            </ElButton>
            <ElButton
              v-if="row.has_graph"
              link
              type="primary"
              @click="emit('navigateGraph', row.id)"
            >
              图谱
            </ElButton>
            <ElButton
              v-if="row.has_graph"
              link
              type="primary"
              :icon="Upload"
              @click="openIncrementalDialog(row)"
            >
              增量更新
            </ElButton>
            <ElButton
              link
              type="primary"
              :loading="constructingId === row.id"
              :disabled="constructingId === row.id"
              @click="handleConstructGraph(row)"
            >
              {{ row.has_graph ? '重建图谱' : '构建图谱' }}
            </ElButton>
            <ElButton
              link
              type="primary"
              @click="handleEditSchema(row)"
            >
              Schema
            </ElButton>
            <ElButton link type="danger" :icon="Trash2" @click="handleDelete(row)">
              删除
            </ElButton>
          </template>
        </template>
      </ElTableColumn>
    </ElTable>

    <UploadDialog
      ref="uploadDialogRef"
      :kb-id="kbId"
      @complete="handleUploadComplete"
    />
    <SchemaEditor ref="schemaEditorRef" :kb-id="kbId" @updated="loadFiles" />

    <ElDialog
      v-model="incrementalDialogVisible"
      title="增量更新"
      width="420px"
      :close-on-click-modal="false"
    >
      <div style="padding: 8px 0">
        <p style="margin: 0 0 12px; font-size: 14px; color: var(--el-text-color-secondary);">
          选择新增的文本文件，系统将自动构建新图谱并合并到现有图谱中。
        </p>
        <ElUpload
          drag
          :auto-upload="false"
          :show-file-list="true"
          :limit="1"
          :on-change="handleIncrementalUpload"
          accept=".txt,.md,.doc,.docx,.pdf"
        >
          <template #default>
            <div style="padding: 20px 0">
              <Upload style="font-size: 32px; color: var(--el-text-color-secondary); margin-bottom: 8px;" />
              <div style="font-size: 14px; color: var(--el-text-color-secondary);">
                拖拽文件到此处，或 <em style="color: var(--el-color-primary); font-style: normal;">点击选择</em>
              </div>
            </div>
          </template>
        </ElUpload>
      </div>
    </ElDialog>

    <ElDialog
      v-model="contentDialogVisible"
      :title="'文本内容 - ' + contentFilename"
      width="80vw"
      top="5vh"
      :close-on-click-modal="false"
    >
      <pre
        v-loading="contentLoading"
        class="content-viewer"
      >{{ contentText || '(无文本内容)' }}</pre>
    </ElDialog>

    <ElDialog
      v-model="showProgressDialog"
      title="构建图谱"
      :close-on-click-modal="false"
      :show-close="false"
      width="400px"
    >
      <div style=" padding: 20px;text-align: center">
        <ElProgress
          :percentage="progress"
          :status="progress === 100 ? 'success' : undefined"
          :stroke-width="12"
        />
        <p style="margin-top: 12px; color: var(--el-text-color-secondary)">
          {{ progressMessage || '正在构建图谱...' }}
        </p>
      </div>
    </ElDialog>
  </div>
</template>

<style scoped>
.files-tab {
  padding: 16px 4px;
}

.tab-toolbar {
  margin-bottom: 12px;
}

.merged-label {
  font-weight: 600;
}

.content-viewer {
  margin: 0;
  padding: 16px;
  max-height: 65vh;
  overflow: auto;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-wrap: break-word;
}
</style>
