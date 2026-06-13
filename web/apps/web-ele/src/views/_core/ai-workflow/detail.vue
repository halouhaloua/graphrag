<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { VueFlow } from '@vue-flow/core';
import '@vue-flow/core/dist/style.css';
// ✅ 移除了 @vue-flow/background，不再需要它
import { Controls } from '@vue-flow/controls';
import { MiniMap } from '@vue-flow/minimap';

import { ElMessageBox } from 'element-plus';

import { createWorkflowDefApi } from '#/api/core/ai-workflow';

import { useWorkflowEditor } from './editor/composables/useWorkflowEditor';
import WorkflowHeader from './editor/WorkflowHeader.vue';
import WorkflowToolbar from './editor/WorkflowToolbar.vue';
import NodeConfigPanel from './editor/panels/NodeConfigPanel.vue';
import WorkflowNode from './editor/nodes/WorkflowNode.vue';
import NodeSelectorPanel from './editor/nodes/NodeSelectorPanel.vue';

defineOptions({ name: 'AiWorkflowDetail' });

const route = useRoute();
const router = useRouter();

let workflowId = route.params.id as string;

const creating = ref(false);
const showNodeSelector = ref(true);

// ✅ 移除了 viewport 相关的监听和计算，完全不需要了

const {
  nodes,
  edges,
  selectedNode,
  workflow,
  loading,
  saving,
  showMinimap,
  canUndo,
  canRedo,
  init,
  save,
  publish,
  run,
  undo,
  redo,
  onDrop,
  onConnect,
  onNodeClick,
  onPaneClick,
  updateNodeParams,
  updateWorkflowName,
  addNodeAtCenter,
  deleteSelectedNode,
} = useWorkflowEditor(workflowId);

onMounted(async () => {
  if (workflowId === 'new') {
    await showCreateDialog();
  } else {
    await init();
  }
});

async function showCreateDialog() {
  try {
    const { value } = await ElMessageBox.prompt('请输入工作流名称', '新建工作流', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputValue: '新建工作流',
      inputValidator: (v: string) => (v ? true : '名称不能为空'),
    });
    creating.value = true;
    try {
      const def = await createWorkflowDefApi({ name: value || '新建工作流' });
      workflowId = def.id;
      router.replace(`/ai-platform/workflow/${def.id}`);
      await init();
    } finally {
      creating.value = false;
    }
  } catch {
    router.push('/ai-platform/workflow');
  }
}

const goBack = () => router.push('/ai-platform/workflow');

async function handlePublish(publishFlag: boolean) {
  if (!workflow.value?.id) {
    const savedId = await save();
    if (savedId) {
      await publish(true);
    }
    return;
  }
  await publish(publishFlag);
}

async function handleRun() {
  if (!workflow.value?.is_published) {
    await handlePublish(true);
  }
  await run();
}

function handleAddNode() {
  showNodeSelector.value = !showNodeSelector.value;
}

function onSelectNode(type: string) {
  addNodeAtCenter(type);
  // 保持面板打开，允许连续添加
}
</script>

<template>
  <div class="workflow-editor" v-loading="loading || creating">
    <WorkflowHeader
      :workflow="workflow"
      :saving="saving"
      @back="goBack"
      @publish="handlePublish"
      @run="handleRun"
      @update-name="updateWorkflowName"
    />

    <div class="workflow-editor__body">
      <div class="workflow-editor__canvas">
        <VueFlow
          v-model:nodes="nodes"
          v-model:edges="edges"
          :node-types="{ workflow: WorkflowNode }"
          :default-edge-options="{
            type: 'smoothstep',
            animated: false,
            style: { stroke: '#94a3b8', strokeWidth: 2 },
          }"
          fit-view-on-init
          @drop="onDrop"
          @dragover.prevent
          @connect="onConnect"
          @node-click="(e: any) => onNodeClick(e.node)"
          @pane-click="onPaneClick"
        >
          <!-- ✅ 移除了 <Background> 组件，改用纯 CSS 背景 -->

          <MiniMap
            v-if="showMinimap"
            position="bottom-right"
            :node-color="(node: any) => node.data?.color || '#64748b'"
            :mask-color="'rgba(0,0,0,0.08)'"
          />
          <Controls position="bottom-left" />
        </VueFlow>

        <NodeConfigPanel
          v-if="selectedNode"
          :selected-node="selectedNode"
          @update-params="updateNodeParams"
          @delete-node="deleteSelectedNode"
          @close="onPaneClick"
        />
      </div>
    </div>

    <WorkflowToolbar
      :can-undo="canUndo"
      :can-redo="canRedo"
      :show-minimap="showMinimap"
      @undo="undo"
      @redo="redo"
      @fit-view="() => {}"
      @zoom-to-1="() => {}"
      @toggle-minimap="showMinimap = !showMinimap"
      @add-node="handleAddNode"
    />

    <NodeSelectorPanel
      v-if="showNodeSelector"
      @close="showNodeSelector = false"
      @add-node="onSelectNode"
    />
  </div>
</template>

<style>
/* 全局容器 */
.workflow-editor {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.workflow-editor__body {
  flex: 1;
  display: flex;
  overflow: hidden;
  position: relative;
}

/* ✅ 核心：在这里设置固定点阵背景 */
.workflow-editor__canvas {
  flex: 1;
  position: relative;
  /* 背景色 */
  background-color: #f8fafc;
  /* 绘制圆点：颜色 #cbd5e1，半径 1.5px */
  background-image: radial-gradient(circle, #cbd5e1 1.5px, transparent 1.5px);
  /* 固定间距 32px */
  background-size: 32px 32px;
  /* 默认就是相对于屏幕固定的，不需要写 background-position */
}

/* 确保 VueFlow 内部的画布背景透明，透出底层的 CSS 点阵 */
.workflow-editor__canvas .vue-flow {
  width: 100%;
  height: 100%;
  background: transparent !important;
}

.workflow-editor__canvas .vue-flow__pane {
  background: transparent !important;
}

/* 节点和连线样式 */
.vue-flow__node {
  cursor: pointer;
}

.vue-flow__edge-path {
  stroke-width: 2;
}
</style>