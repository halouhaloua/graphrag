<script lang="ts" setup>
import type { WriterDocument } from '#/api/core/rag';
import { FileTextOutlined } from '@vben/icons';
import { ElButton } from 'element-plus';

defineProps<{
  document: WriterDocument;
}>();

const emit = defineEmits<{
  open: [doc: WriterDocument];
  delete: [docId: string];
}>();
</script>

<template>
  <div class="writer-doc-card" @click="emit('open', document)">
    <div class="doc-card-icon">
      <FileTextOutlined />
    </div>
    <div class="doc-card-body">
      <div class="doc-card-title">{{ document.title || '未命名文档' }}</div>
      <div class="doc-card-time">{{ new Date(document.sys_update_datetime).toLocaleString() }}</div>
    </div>
    <ElButton
      class="doc-card-delete"
      link
      size="small"
      @click.stop="emit('delete', document.id)"
    >
      删除
    </ElButton>
  </div>
</template>

<style scoped>
.writer-doc-card {
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 16px;
  margin-top: 12px;
  max-width: 300px;
  min-height: 120px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 20px;
  cursor: pointer;
  transition: all 0.25s ease;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02);
}

.writer-doc-card:hover {
  transform: translateY(-3px);
  background: var(--el-fill-color-lighter);
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.1);
}

.doc-card-icon {
  font-size: 24px;
  color: var(--el-color-primary);
  margin-bottom: 20px;
  transition: transform 0.2s;
  align-self: flex-start;
}

.writer-doc-card:hover .doc-card-icon {
  transform: scale(1.02);
}

.doc-card-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.doc-card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  line-height: 1.2;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}

.doc-card-time {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  display: flex;
  align-items: center;
  gap: 4px;
}

.doc-card-time::before {
  content: '创建时间：';
  font-size: 11px;
  opacity: 0.9;
}

.doc-card-delete {
  position: absolute;
  top: 12px;
  right: 12px;
  opacity: 0;
  transition: opacity 0.2s ease, color 0.2s;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  padding: 4px;
}

.doc-card-delete:hover {
  color: var(--el-color-danger);
  background: transparent !important;
}

.writer-doc-card:hover .doc-card-delete {
  opacity: 1;
}
</style>