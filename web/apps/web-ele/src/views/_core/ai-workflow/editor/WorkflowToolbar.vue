<script setup lang="ts">
import { Map, Maximize, Plus, Redo2, Undo2, ZoomIn } from '@vben/icons';
import { ElButton, ElDivider, ElTooltip } from 'element-plus';

defineProps<{
  canUndo: boolean;
  canRedo: boolean;
  showMinimap: boolean;
}>();

const emit = defineEmits<{
  undo: [];
  redo: [];
  fitView: [];
  zoomTo1: [];
  toggleMinimap: [];
  addNode: [];
}>();
</script>

<template>
  <div class="workflow-toolbar">
    <ElTooltip content="撤销" placement="top">
      <ElButton text size="small" :disabled="!canUndo" @click="emit('undo')">
        <Undo2 class="h-4 w-4" />
      </ElButton>
    </ElTooltip>
    <ElTooltip content="重做" placement="top">
      <ElButton text size="small" :disabled="!canRedo" @click="emit('redo')">
        <Redo2 class="h-4 w-4" />
      </ElButton>
    </ElTooltip>

    <ElDivider direction="vertical" />

    <ElTooltip content="适应画布" placement="top">
      <ElButton text size="small" @click="emit('fitView')">
        <Maximize class="h-4 w-4" />
      </ElButton>
    </ElTooltip>
    <ElTooltip content="缩放到1:1" placement="top">
      <ElButton text size="small" @click="emit('zoomTo1')">
        <ZoomIn class="h-4 w-4" />
      </ElButton>
    </ElTooltip>
    <ElTooltip :content="showMinimap ? '隐藏小地图' : '显示小地图'" placement="top">
      <ElButton
        text
        size="small"
        :type="showMinimap ? 'primary' : 'default'"
        @click="emit('toggleMinimap')"
      >
        <Map class="h-4 w-4" />
      </ElButton>
    </ElTooltip>

    <ElDivider direction="vertical" />

    <ElButton size="small" @click="emit('addNode')">
      <Plus class="mr-1 h-3.5 w-3.5" />
      添加节点
    </ElButton>
  </div>
</template>

<style scoped>
.workflow-toolbar {
  position: absolute;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 2px;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  padding: 4px 8px;
}
</style>
