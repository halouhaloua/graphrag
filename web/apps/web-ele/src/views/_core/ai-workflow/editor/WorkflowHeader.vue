<script setup lang="ts">
import type { WorkflowDef } from '#/api/core/ai-workflow';

import { ArrowLeft, Copy, Play, Send } from '@vben/icons';
import {
  ElButton,
  ElMessage,
  ElTag,
  ElTooltip,
} from 'element-plus';

const props = defineProps<{
  workflow: WorkflowDef | null;
  saving: boolean;
}>();

const emit = defineEmits<{
  back: [];
  publish: [publish: boolean];
  run: [];
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

function copyAccessUrl() {
  if (!props.workflow?.workflow_route) return;
  const prefix = props.workflow.workflow_type === 'ai_workflow' ? 'ai' : 'app';
  const url = `/wf/${prefix}/${props.workflow.workflow_route}`;
  navigator.clipboard.writeText(window.location.origin + url);
  ElMessage.success('访问链接已复制');
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
      <div class="workflow-header__title-text">
        {{ workflow?.name || '未命名工作流' }}
      </div>
      <ElTag
        :type="workflow?.workflow_type === 'ai_workflow' ? 'primary' : 'warning'"
        size="small"
        effect="light"
      >
        {{ workflow?.workflow_type === 'ai_workflow' ? 'AI' : '应用' }}
      </ElTag>
      <ElTag v-if="workflow?.is_published" type="success" size="small" effect="dark">
        已发布
      </ElTag>
      <ElTag v-else type="warning" size="small" effect="dark">
        未发布
      </ElTag>
      <template v-if="workflow?.is_published && workflow?.workflow_route">
        <ElTag size="small" type="info" effect="plain" class="route-tag">
          /{{ workflow.workflow_type === 'ai_workflow' ? 'ai' : 'app' }}/{{ workflow.workflow_route }}
        </ElTag>
        <ElTooltip content="复制访问链接" placement="bottom">
          <ElButton text size="small" @click="copyAccessUrl">
            <Copy class="h-3.5 w-3.5" />
          </ElButton>
        </ElTooltip>
      </template>
    </div>

    <div class="workflow-header__right">

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

.workflow-header__title-text {
  font-size: 14px;
  padding: 0 8px;
  line-height: 28px; /* 和 small 尺寸输入框高度对齐 */
  cursor: pointer;
}

.route-tag {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 10px;
}
</style>
