<script setup lang="ts">
import { ElButton } from 'element-plus';
import { Columns2, Database, Edit, Eye, PanelLeft } from '@vben/icons';

defineProps<{
  collapsed: boolean;
  activeNav: 'preview' | 'edit' | 'split' | 'addToKb';
}>();

const emit = defineEmits<{
  'update:collapsed': [value: boolean];
  'update:activeNav': [value: 'preview' | 'edit' | 'split' | 'addToKb'];
}>();
</script>

<template>
  <div v-if="!collapsed" class="sidebar">
    <div class="sidebar-header">
      <span class="sidebar-title">功能导航</span>
      <div class="sidebar-actions">
        <ElButton
          :icon="PanelLeft"
          circle
          size="small"
          @click="emit('update:collapsed', true)"
        />
      </div>
    </div>
    <div class="sidebar-body">
      <div
        class="nav-item"
        :class="{ active: activeNav === 'preview' }"
        @click="emit('update:activeNav', 'preview')"
      >
        <Eye class="size-4" />
        <span>文件预览</span>
      </div>
      <div
        class="nav-item"
        :class="{ active: activeNav === 'edit' }"
        @click="emit('update:activeNav', 'edit')"
      >
        <Edit class="size-4" />
        <span>文本编辑</span>
      </div>
      <div
        class="nav-item"
        :class="{ active: activeNav === 'split' }"
        @click="emit('update:activeNav', 'split')"
      >
        <Columns2 class="size-4" />
        <span>双栏模式</span>
      </div>
      <div
        class="nav-item"
        :class="{ active: activeNav === 'addToKb' }"
        @click="emit('update:activeNav', 'addToKb')"
      >
        <Database class="size-4" />
        <span>添加到知识库</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sidebar {
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  width: 220px;
  overflow: hidden;
  background: var(--el-bg-color-overlay);
  border-radius: 8px;
  transition: width 0.25s ease;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}

.sidebar-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.sidebar-actions {
  display: flex;
  gap: 4px;
  align-items: center;
}

.sidebar-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  margin-bottom: 2px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: var(--el-text-color-regular);
  transition: all 0.15s;
}

.nav-item:hover {
  background: var(--el-fill-color-light);
}

.nav-item.active {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 500;
}
</style>
