<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { VueFlow } from '@vue-flow/core';
import '@vue-flow/core/dist/style.css';
import { Background, BackgroundVariant } from '@vue-flow/background';
import { Controls } from '@vue-flow/controls';
import { MiniMap } from '@vue-flow/minimap';

import { ElMessage, ElMessageBox } from 'element-plus';

import { createWorkflowDefApi } from '#/api/core/ai-workflow';

import { useWorkflowEditor } from './editor/composables/useWorkflowEditor';
import WorkflowHeader from './editor/WorkflowHeader.vue';
import WorkflowToolbar from './editor/WorkflowToolbar.vue';
import NodeConfigPanel from './editor/panels/NodeConfigPanel.vue';
import NodeSelectorPanel from './editor/nodes/NodeSelectorPanel.vue';
import WorkflowNode from './editor/nodes/WorkflowNode.vue';

defineOptions({ name: 'AiWorkflowDetail' });

const route = useRoute();
const router = useRouter();

let workflowId = route.params.id as string;

const creating = ref(false);

const {
  nodes,
  edges,
  selectedNode,
  workflow,
  loading,
  saving,
  showMinimap,
  hasUnsavedChanges,
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

async function handleSave() {
  await save();
}

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
  addNodeAtCenter('chat');
}
</script>

<template>
  <div class="workflow-editor" v-loading="loading || creating">
    <WorkflowHeader
      :workflow="workflow"
      :has-unsaved-changes="hasUnsavedChanges"
      :saving="saving"
      @back="goBack"
      @save="handleSave"
      @publish="handlePublish"
      @run="handleRun"
      @version-history="ElMessage.info('版本历史功能开发中')"
      @update-name="updateWorkflowName"
    />

    <div class="workflow-editor__body">
      <NodeSelectorPanel />

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
          <Background :gap="20" :variant="BackgroundVariant.Dots" color="#e2e8f0" />
          <MiniMap
            v-if="showMinimap"
            position="bottom-right"
            :node-color="(node: any) => node.data?.color || '#64748b'"
            :mask-color="'rgba(0,0,0,0.08)'"
          />
          <Controls position="bottom-left" />
        </VueFlow>
      </div>

      <NodeConfigPanel
        :selected-node="selectedNode"
        @update-params="updateNodeParams"
      />
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
  </div>
</template>

<style>
.workflow-editor {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f8fafc;
  overflow: hidden;
}
.workflow-editor__body {
  flex: 1;
  display: flex;
  overflow: hidden;
  position: relative;
}
.workflow-editor__canvas {
  flex: 1;
  position: relative;
}
.workflow-editor__canvas .vue-flow {
  width: 100%;
  height: 100%;
}
.vue-flow__node {
  cursor: pointer;
}
.vue-flow__edge-path {
  stroke-width: 2;
}
</style>
