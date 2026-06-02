<script lang="ts" setup>
import { ref } from 'vue';
import { ElButton, ElDialog, ElMessage, ElRadio, ElRadioGroup, ElUpload } from 'element-plus';
import { uploadFilesApi } from '#/api/core/rag';

const props = defineProps<{ kbId: string }>();
const emit = defineEmits<{ complete: [] }>();

const visible = ref(false);
const fileList = ref<any[]>([]);
const schemaFile = ref<File | null>(null);
const uploading = ref(false);
const schemaPreset = ref<'none' | 'chinese' | 'english' | 'custom'>('none');

const PRESET_SCHEMAS: Record<string, object> = {
  chinese: {
    Nodes: ['人物', '组织', '地点', '事件', '时间', '概念'],
    Relations: ['属于', '位于', '创建', '参与', '影响', '包含', '相关'],
    Attributes: ['名称', '描述', '日期', '数量', '类型'],
  },
  english: {
    Nodes: ['Person', 'Organization', 'Location', 'Event', 'Date', 'Concept', 'Product', 'Technology'],
    Relations: ['belongs_to', 'located_in', 'created_by', 'participates_in', 'influences', 'contains', 'related_to', 'produces'],
    Attributes: ['name', 'description', 'date', 'quantity', 'status', 'type'],
  },
};

function open() {
  visible.value = true;
  fileList.value = [];
  schemaFile.value = null;
  schemaPreset.value = 'none';
}

function handlePresetChange(val: string | number | boolean | undefined) {
  schemaPreset.value = (val || 'none') as typeof schemaPreset.value;
  if (val === 'chinese' || val === 'english') {
    const json = PRESET_SCHEMAS[val];
    const blob = new Blob([JSON.stringify(json, null, 2)], { type: 'application/json' });
    schemaFile.value = new File([blob], 'schema.json', { type: 'application/json' });
  } else if (val === 'none') {
    schemaFile.value = null;
  }
}

async function handleUpload() {
  if (fileList.value.length === 0) {
    ElMessage.warning('请至少选择一个文件');
    return;
  }
  uploading.value = true;
  try {
    const files = fileList.value.map((f) => f.raw);
    await uploadFilesApi(props.kbId, files, schemaFile.value);
    ElMessage.success(`上传成功 (${files.length} 个文件)`);
    visible.value = false;
    emit('complete');
  } catch (err: any) {
    ElMessage.error(err.message || '上传失败');
  } finally {
    uploading.value = false;
  }
}

function handleSchemaSelect(file: File | undefined) {
  schemaFile.value = file || null;
  if (schemaFile.value) schemaPreset.value = 'custom';
}

defineExpose({ open });
</script>

<template>
  <ElDialog
    v-model="visible"
    title="上传文件"
    width="560px"
    :close-on-click-modal="false"
  >
    <div class="upload-section">
      <label class="section-label">选择文档文件</label>
      <ElUpload
        v-model:file-list="fileList"
        multiple
        drag
        :auto-upload="false"
        accept=".txt,.pdf,.doc,.docx,.csv,.xls,.xlsx,.md"
      >
        <div class="upload-hint">
          <div class="upload-icon">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
          </div>
          <div>拖拽文件到此处，或点击选择</div>
          <div class="upload-types">支持: TXT, PDF, DOC, DOCX, CSV, XLS, XLSX, MD</div>
        </div>
      </ElUpload>
    </div>

    <div class="upload-section">
      <label class="section-label">Schema 定义（可选）</label>
      <ElRadioGroup :model-value="schemaPreset" @change="handlePresetChange">
        <ElRadio value="none">不设置</ElRadio>
        <ElRadio value="chinese">中文预设</ElRadio>
        <ElRadio value="english">English Preset</ElRadio>
        <ElRadio value="custom">自定义上传</ElRadio>
      </ElRadioGroup>
      <div v-if="schemaPreset === 'chinese' || schemaPreset === 'english'" class="preset-preview">
        <div class="preset-label">
          {{ schemaPreset === 'chinese' ? '中文预设内容' : 'English Preset' }}
        </div>
        <pre class="preset-json">{{ JSON.stringify(PRESET_SCHEMAS[schemaPreset], null, 2) }}</pre>
      </div>
      <div v-if="schemaPreset === 'custom'" class="schema-upload-area">
        <ElUpload
          :auto-upload="false"
          accept=".json"
          :limit="1"
          :on-change="(f) => handleSchemaSelect(f.raw)"
          :on-remove="() => handleSchemaSelect(undefined)"
        >
          <template #trigger>
            <ElButton>选择 Schema JSON</ElButton>
          </template>
          <template #tip>
            <div class="el-upload__tip">JSON 格式: {"Nodes":[], "Relations":[], "Attributes":[]}</div>
          </template>
        </ElUpload>
      </div>
    </div>

    <template #footer>
      <ElButton @click="visible = false">取消</ElButton>
      <ElButton type="primary" :loading="uploading" @click="handleUpload">
        {{ uploading ? '上传中...' : '开始上传' }}
      </ElButton>
    </template>
  </ElDialog>
</template>

<style scoped>
.upload-section {
  margin-bottom: 20px;
}

.section-label {
  display: block;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 600;
}

.upload-hint {
  padding: 20px;
  text-align: center;
}

.upload-icon {
  margin-bottom: 8px;
  font-size: 40px;
}

.upload-types {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.upload-section :deep(.el-radio-group) {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.schema-upload-area {
  margin-top: 8px;
}

.preset-preview {
  margin-top: 8px;
  padding: 10px 12px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
}

.preset-label {
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}

.preset-json {
  margin: 0;
  font-family: monospace;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  color: var(--el-text-color-regular);
}
</style>
