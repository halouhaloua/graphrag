<script setup lang="ts">
import type { WorkflowDef } from '#/api/core/ai-workflow';

import { ArrowLeft, History, Play, Send } from '@vben/icons';
import {
  ElButton,
  ElInput,
  ElMessage,
  ElTag,
  ElTooltip,
} from 'element-plus';

const props = defineProps<{
  workflow: WorkflowDef | null;
  hasUnsavedChanges: boolean;
  saving: boolean;
}>();

const emit = defineEmits<{
  back: [];
  save: [];
  publish: [publish: boolean];
  run: [];
  versionHistory: [];
  updateName: [name: string];
}>();

function handlePublish() {
  if (!props.workflow) return;
  emit('publish', !props.workflow.is_published);
}

function handleRun() {
  if (!props.workflow) return;
  if (!props.workflow.is_published) {
    ElMessage.warning('请先发布工作流');
    return;
  }
  emit('run');
}
</script>

<template>
  <header class="workflow-header">
    <div class="workflow-header__left">
      <ElTooltip content="返回列表" placement="bottom">
        <ElButton text class="!text-foreground" @click="emit('back')">
          <ArrowLeft class="h-4 w-4" />
        </ElButton>
      </ElTooltip>
      <ElInput
        :model-value="workflow?.name || '未命名工作流'"
        class="workflow-header__title-input"
        size="small"
        @update:model-value="emit('updateName', $event)"
      />
      <ElTag v-if="workflow?.is_published" type="success" size="small" effect="dark">
        已发布
      </ElTag>
      <ElTag v-else type="warning" size="small" effect="dark">
        未发布
      </ElTag>
      <ElTag type="primary" size="small" effect="plain">
        v{{ workflow?.version || 1 }} · 编辑中
      </ElTag>
    </div>

    <div class="workflow-header__right">
      <span
        class="workflow-header__save-status"
        :class="{ 'is-dirty': hasUnsavedChanges }"
      >
        {{ hasUnsavedChanges ? '有未保存的更改' : '已保存' }}
      </span>

      <ElTooltip content="版本历史" placement="bottom">
        <ElButton
          text
          class="!text-foreground"
          size="small"
          @click="emit('versionHistory')"
        >
          <History class="h-4 w-4" />
        </ElButton>
      </ElTooltip>

      <ElButton
        type="primary"
        :class="workflow?.is_published ? '' : 'is-outlined'"
        size="small"
        :loading="saving"
        @click="handlePublish"
      >
        <Send v-if="!workflow?.is_published" class="mr-1 h-3.5 w-3.5" />
        {{ workflow?.is_published ? '取消发布' : '发布' }}
      </ElButton>

      <ElButton
        type="primary"
        size="small"
        :disabled="!workflow?.is_published"
        @click="handleRun"
      >
        <Play class="mr-1 h-3.5 w-3.5" />
        运行
      </ElButton>
    </div>
  </header>
</template>

<style scoped>
.workflow-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 52px;
  padding: 0 16px;
  background: #fff;
  border-bottom: 1px solid #e2e8f0;
  flex-shrink: 0;
  z-index: 20;
}
.workflow-header__left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}
.workflow-header__title-input {
  width: 200px;
}
.workflow-header__right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.workflow-header__save-status {
  font-size: 12px;
  color: #22c55e;
  transition: color 0.2s;
}
.workflow-header__save-status.is-dirty {
  color: #f59e0b;
}
</style>
