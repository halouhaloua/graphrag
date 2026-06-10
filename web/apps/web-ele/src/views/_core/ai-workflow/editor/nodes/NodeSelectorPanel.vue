<script setup lang="ts">
import { IconifyIcon } from '@vben/icons';
import { ElInput } from 'element-plus';
import { computed, ref } from 'vue';

import { NODE_CATEGORIES, NODE_TYPE_MAP, type NodeTypeMeta } from './index';

const search = ref('');

const groupedNodes = computed(() => {
  const q = search.value.toLowerCase().trim();
  const all = Object.values(NODE_TYPE_MAP).filter((n) => {
    if (n.type === '_start' || n.type === '_end') return false;
    if (!q) return true;
    return n.label.toLowerCase().includes(q) || n.description.toLowerCase().includes(q);
  });
  return NODE_CATEGORIES.map((cat) => ({
    ...cat,
    nodes: all.filter((n) => n.category === cat.key),
  })).filter((g) => g.nodes.length > 0);
});

function onDragStart(event: DragEvent, meta: NodeTypeMeta) {
  if (event.dataTransfer) {
    event.dataTransfer.setData('application/vnd-workflow-node', meta.type);
    event.dataTransfer.effectAllowed = 'move';
  }
}
</script>

<template>
  <aside class="node-selector-panel">
    <div class="panel-header">节点</div>
    <div class="panel-search">
      <ElInput
        v-model="search"
        placeholder="搜索节点..."
        size="small"
        clearable
      />
    </div>
    <div class="panel-body">
      <div
        v-for="group in groupedNodes"
        :key="group.key"
        class="node-group"
      >
        <div class="node-group__title">{{ group.label }}</div>
        <div
          v-for="meta in group.nodes"
          :key="meta.type"
          class="node-item"
          draggable="true"
          @dragstart="onDragStart($event, meta)"
        >
          <div class="node-item__icon" :style="{ background: meta.color }">
            <IconifyIcon :icon="`lucide:${meta.icon}`" class="h-4 w-4 text-white" />
          </div>
          <div class="node-item__info">
            <div class="node-item__name">{{ meta.label }}</div>
            <div class="node-item__desc">{{ meta.description }}</div>
          </div>
        </div>
      </div>
      <div v-if="groupedNodes.length === 0" class="panel-empty">
        未找到匹配的节点
      </div>
    </div>
  </aside>
</template>

<style scoped>
.node-selector-panel {
  width: 220px;
  background: #fff;
  border-right: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
.panel-header {
  padding: 12px 14px 8px;
  font-weight: 600;
  font-size: 14px;
  color: #1e293b;
}
.panel-search {
  padding: 0 10px 8px;
}
.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px 12px;
}
.panel-empty {
  text-align: center;
  color: #94a3b8;
  font-size: 12px;
  padding: 24px 0;
}
.node-group {
  margin-bottom: 8px;
}
.node-group__title {
  font-size: 11px;
  font-weight: 600;
  color: #94a3b8;
  text-transform: uppercase;
  padding: 4px 6px;
  letter-spacing: 0.5px;
}
.node-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  margin-bottom: 2px;
  border-radius: 8px;
  cursor: grab;
  transition: background 0.12s;
  user-select: none;
}
.node-item:hover {
  background: #f1f5f9;
}
.node-item:active {
  cursor: grabbing;
  background: #e2e8f0;
}
.node-item__icon {
  width: 30px;
  height: 30px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.node-item__info {
  min-width: 0;
}
.node-item__name {
  font-size: 12px;
  font-weight: 500;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.node-item__desc {
  font-size: 10px;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
