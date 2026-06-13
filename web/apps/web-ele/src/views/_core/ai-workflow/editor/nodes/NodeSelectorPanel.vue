<script setup lang="ts">
import { IconifyIcon } from '@vben/icons';
import { computed, onMounted, onBeforeUnmount, ref } from 'vue';

import { NODE_CATEGORIES, NODE_TYPE_MAP, type NodeTypeMeta } from './index';

const emit = defineEmits<{
  close: [];
  addNode: [type: string];
}>();

const search = ref('');

const groupedNodes = computed(() => {
  const q = search.value.toLowerCase().trim();
  const all = Object.values(NODE_TYPE_MAP).filter((n) => {
    if (n.type === '_start' || n.type === '_end') return false;
    if (!q) return true;
    return (
      n.label.toLowerCase().includes(q) ||
      n.description.toLowerCase().includes(q)
    );
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

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    emit('close');
  }
}

onMounted(() => {
  document.addEventListener('keydown', onKeyDown);
});

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeyDown);
});
</script>

<template>
  <div class="palette-sidebar">
    <div class="palette-card">
      <div class="palette-header">
        <span class="palette-title">节点</span>
        <button class="palette-close" @click="emit('close')">
          <IconifyIcon icon="lucide:x" class="h-4 w-4" />
        </button>
      </div>

      <div class="palette-search">
        <!-- <IconifyIcon icon="lucide:search" class="palette-search-icon" /> -->
        <input
          v-model="search"
          placeholder="搜索节点..."
          class="palette-search-input"
        />
      </div>

      <div class="palette-body">
        <div
          v-for="group in groupedNodes"
          :key="group.key"
          class="palette-group"
        >
          <div class="palette-group__title">{{ group.label }}</div>
          <div
            v-for="meta in group.nodes"
            :key="meta.type"
            class="palette-item"
            draggable="true"
            @dragstart="onDragStart($event, meta)"
            @click="emit('addNode', meta.type)"
          >
            <div
              class="palette-item__icon"
              :style="{ background: meta.color }"
            >
              <IconifyIcon
                :icon="`lucide:${meta.icon}`"
                class="h-4 w-4 text-white"
              />
            </div>
            <div class="palette-item__info">
              <div class="palette-item__name">{{ meta.label }}</div>
              <div class="palette-item__desc">{{ meta.description }}</div>
            </div>
          </div>
        </div>
        <div v-if="groupedNodes.length === 0" class="palette-empty">
          未找到匹配的节点
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── sidebar 容器 ── */
.palette-sidebar {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  z-index: 40;
  pointer-events: none;
}

/* ── 节点卡片 ── */
.palette-card {
  position: absolute;
  left: 24px;
  top: 8vh;
  bottom: 8vh;
  width: 264px;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.15);
  overflow: hidden;
  pointer-events: auto;
  animation: paletteIn 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes paletteIn {
  from {
    opacity: 0;
    transform: translateX(-20px) scale(0.96);
  }
  to {
    opacity: 1;
    transform: translateX(0) scale(1);
  }
}

/* ── header ── */
.palette-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 16px 10px;
  flex-shrink: 0;
}
.palette-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.3px;
}
.palette-close {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.12s;
}
.palette-close:hover {
  background: #f1f5f9;
  color: #1e293b;
}

/* ── search ── */
.palette-search {
  position: relative;
  padding: 0 12px 12px;
  flex-shrink: 0;
}
.palette-search-icon {
  position: absolute;
  left: 22px;
  top: 50%;
  transform: translateY(-50%);
  width: 14px;
  height: 14px;
  color: #94a3b8;
  pointer-events: none;
}
.palette-search-input {
  width: 100%;
  padding: 8px 12px 8px 8px;
  font-size: 13px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #f8fafc;
  color: #1e293b;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
  box-sizing: border-box;
}
.palette-search-input::placeholder {
  color: #94a3b8;
}
.palette-search-input:focus {
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  background: #fff;
}

/* ── body ── */
.palette-body {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px 16px;
}

/* 隐藏滚动条（保留滚动功能） */
.palette-body {
  scrollbar-width: none;
}
.palette-body::-webkit-scrollbar {
  display: none;
}

.palette-empty {
  text-align: center;
  color: #94a3b8;
  font-size: 12px;
  padding: 32px 0;
}

/* ── group ── */
.palette-group {
  margin-bottom: 4px;
}
.palette-group__title {
  font-size: 10px;
  font-weight: 700;
  color: #94a3b8;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  padding: 10px 8px 6px;
}

/* ── item ── */
.palette-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 8px;
  border-radius: 10px;
  cursor: grab;
  user-select: none;
  transition: background 0.12s, transform 0.12s;
}
.palette-item:hover {
  background: #f1f5f9;
  transform: translateX(3px);
}
.palette-item:active {
  cursor: grabbing;
  background: #e2e8f0;
  transform: translateX(1px);
}
.palette-item__icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.palette-item__info {
  min-width: 0;
}
.palette-item__name {
  font-size: 12px;
  font-weight: 600;
  color: #0f172a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}
.palette-item__desc {
  font-size: 10px;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 1px;
}
</style>
