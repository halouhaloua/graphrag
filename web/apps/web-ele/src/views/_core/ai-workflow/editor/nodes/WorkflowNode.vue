<script setup lang="ts">
import type { NodeProps } from '@vue-flow/core';

import { Handle, Position } from '@vue-flow/core';
import { computed } from 'vue';

import { IconifyIcon } from '@vben/icons';

import { NODE_TYPE_MAP, getNodeMeta, truncateText, type NodeTypeMeta } from './index';

const props = defineProps<NodeProps>();

const meta = computed(() => (getNodeMeta(props.data?.type) || NODE_TYPE_MAP._end) as NodeTypeMeta);
const showTarget = computed(() => meta.value.inputs > 0);
const showSource = computed(() => meta.value.outputs > 0);

const statusClass = computed(() => {
  if (!props.data?.status) return '';
  if (props.data.status === 'running') return 'is-running';
  if (props.data.status === 'completed') return 'is-completed';
  if (props.data.status === 'failed') return 'is-failed';
  return '';
});

const paramSummary = computed(() => {
  const p = props.data?.params;
  if (!p || Object.keys(p).length === 0) return '';
  const type = props.data.type;
  if (type === 'chat' && p.user_question) return truncateText(p.user_question, 28);
  if (type === 'serper_search' && p.query) return `搜索: ${truncateText(p.query, 22)}`;
  if (type === 'web_crawler' && p.url) return truncateText(p.url, 28);
  if (type === 'api_call' && p.url) return truncateText(p.url, 28);
  if (type === 'python_execute' && p.code) return truncateText(p.code, 28);
  if (type === 'browser_agent' && p.task) return truncateText(p.task, 28);
  if (type === 'weather_forecast') {
    return p.latitude ? `(${p.latitude}, ${p.longitude})` : '';
  }
  return '';
});
</script>

<template>
  <div
    class="workflow-node"
    :class="[`type-${props.data?.type}`, statusClass]"
    :style="{ '--node-color': meta.color }"
  >
    <Handle
      v-if="showTarget"
      type="target"
      :position="Position.Left"
      class="workflow-handle workflow-handle--target"
    />

    <div class="workflow-node__header" :style="{ background: meta.color }">
      <IconifyIcon :icon="`lucide:${meta.icon}`" class="workflow-node__icon" />
      <span class="workflow-node__label">{{ props.data?.label || meta.label }}</span>
    </div>

    <div class="workflow-node__body">
      <template v-if="props.data?.type === '_start'">
        <div class="workflow-node__desc">工作流开始</div>
      </template>
      <template v-else-if="props.data?.type === '_end'">
        <div class="workflow-node__desc">工作流结束</div>
      </template>
      <template v-else-if="paramSummary">
        <div class="workflow-node__desc">{{ paramSummary }}</div>
      </template>
      <template v-else>
        <div class="workflow-node__placeholder">点击配置参数</div>
      </template>
    </div>

    <Handle
      v-if="showSource"
      type="source"
      :position="Position.Right"
      class="workflow-handle workflow-handle--source"
    />
  </div>
</template>

<style scoped>
.workflow-node {
  width: 200px;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08), 0 0 0 1px rgba(0, 0, 0, 0.04);
  overflow: hidden;
  font-size: 12px;
  transition: box-shadow 0.15s, border-color 0.15s;
  cursor: pointer;
}
.workflow-node:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1), 0 0 0 1.5px var(--node-color);
}
.workflow-node.is-running {
  box-shadow: 0 0 0 2px var(--node-color), 0 0 12px rgba(59, 130, 246, 0.3);
  animation: pulse-border 1.5s infinite;
}
.workflow-node.is-completed {
  box-shadow: 0 0 0 2px #22c55e;
}
.workflow-node.is-failed {
  box-shadow: 0 0 0 2px #ef4444;
}
.workflow-node__header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  color: #fff;
}
.workflow-node__icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}
.workflow-node__label {
  font-weight: 600;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.workflow-node__body {
  padding: 10px 12px;
  min-height: 28px;
}
.workflow-node__desc {
  color: #475569;
  line-height: 1.4;
  font-size: 11px;
  word-break: break-all;
}
.workflow-node__placeholder {
  color: #94a3b8;
  font-size: 11px;
  font-style: italic;
}
.workflow-handle {
  width: 10px;
  height: 10px;
  background: #fff;
  border: 2px solid var(--node-color, #94a3b8);
  border-radius: 50%;
  transition: transform 0.15s, border-color 0.15s;
}
.workflow-handle:hover {
  transform: scale(1.4);
  border-color: var(--node-color);
}
.workflow-handle--target {
  left: -5px;
}
.workflow-handle--source {
  right: -5px;
}
@keyframes pulse-border {
  0%,
  100% {
    box-shadow: 0 0 0 2px var(--node-color), 0 0 6px rgba(59, 130, 246, 0.2);
  }
  50% {
    box-shadow: 0 0 0 3px var(--node-color), 0 0 16px rgba(59, 130, 246, 0.4);
  }
}
</style>
