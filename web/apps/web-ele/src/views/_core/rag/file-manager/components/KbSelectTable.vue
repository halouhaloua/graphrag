<script setup lang="ts">
import { Database } from '@vben/icons';
import { ElButton, ElPagination, ElTable, ElTableColumn } from 'element-plus';

interface KbItem {
  id: string;
  name: string;
  description?: string;
}

defineProps<{
  kbList: KbItem[];
  loading: boolean;
  addingToKb: boolean;
  page: number;
  pageSize: number;
  total: number;
}>();

const emit = defineEmits<{
  add: [kbId: string];
  'update:page': [value: number];
  'update:pageSize': [value: number];
}>();

function handleRowClick(row: KbItem) {
  emit('add', row.id);
}
</script>

<template>
  <div class="kb-list-page">
    <div class="kb-list-header">
      <Database class="size-5" />
      <span>选择一个知识库添加到</span>
    </div>
    <ElTable
      v-loading="loading"
      :data="kbList"
      stripe
      style="width: 100%"
      @row-click="handleRowClick"
    >
      <ElTableColumn type="index" width="60" label="序号" />
      <ElTableColumn prop="name" label="知识库名称" min-width="180" />
      <ElTableColumn prop="description" label="描述" min-width="280">
        <template #default="{ row }">
          <span class="kb-desc">{{ row.description || '暂无描述' }}</span>
        </template>
      </ElTableColumn>
      <ElTableColumn label="操作" width="120">
        <template #default="{ row }">
          <ElButton
            size="small"
            type="primary"
            :loading="addingToKb"
            @click.stop="emit('add', row.id)"
          >
            添加
          </ElButton>
        </template>
      </ElTableColumn>
    </ElTable>
    <div class="kb-pagination-wrap">
      <ElPagination
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        :page-sizes="[5, 10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        background
        @current-change="emit('update:page', $event)"
        @size-change="emit('update:pageSize', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.kb-list-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 16px;
}

.kb-list-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 0 0;
  font-size: 15px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.kb-list-header :deep(svg) {
  color: var(--el-color-primary);
}

.kb-desc {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  display: block;
}

.kb-pagination-wrap {
  display: flex;
  justify-content: flex-end;
  padding: 12px 0;
  flex-shrink: 0;
}

.kb-list-page :deep(.el-table) {
  flex: 1;
  min-height: 0;
}

.kb-list-page :deep(.el-table__body-wrapper) {
  overflow-y: auto;
}
</style>
