import type { Edge, Node } from '@vue-flow/core';

import { nanoid } from 'nanoid';
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';

import { ElMessage } from 'element-plus';

import {
  getWorkflowDefDetailApi,
  publishWorkflowDefApi,
  runWorkflowApi,
  updateWorkflowDefApi,
  type WorkflowDef,
  type WorkflowDefEdge,
  type WorkflowDefNode,
} from '#/api/core/ai-workflow';
import { useWorkflowEditorStore } from '#/store/workflow-editor';

import { getNodeMeta } from '../nodes/index';

const DEFAULT_NODE_POSITION = { x: 250, y: 200 };

function createDefaultWorkflowNodes(): Node[] {
  return [
    {
      id: 'start-1',
      type: 'workflow',
      position: { x: 100, y: 250 },
      data: { type: '_start', label: '开始', params: {}, status: '' },
    },
    {
      id: 'end-1',
      type: 'workflow',
      position: { x: 700, y: 250 },
      data: { type: '_end', label: '结束', params: {}, status: '' },
    },
  ];
}

function toFlowNode(n: WorkflowDefNode): Node {
  return {
    id: n.id,
    type: 'workflow',
    position: n.position || { x: 0, y: 0 },
    data: {
      type: n.type,
      label:
        n.type === '_start'
          ? '开始'
          : n.type === '_end'
            ? '结束'
            : getNodeMeta(n.type)?.label || n.type,
      params: n.params || {},
      status: '',
    },
  };
}

function toFlowEdge(e: WorkflowDefEdge): Edge {
  return {
    id: `e-${e.source}-${e.target}`,
    source: e.source,
    target: e.target,
    type: 'smoothstep',
  };
}

function fromFlowNode(n: Node): WorkflowDefNode {
  return {
    id: n.id,
    type: n.data?.type || 'unknown',
    params: n.data?.params || {},
    position: {
      x: Math.round(n.position?.x || 0),
      y: Math.round(n.position?.y || 0),
    },
  };
}

function fromFlowEdge(e: Edge): WorkflowDefEdge {
  return {
    source: e.source,
    target: e.target,
  };
}

export function useWorkflowEditor(workflowId: string) {
  const store = useWorkflowEditorStore();

  const nodes = ref<Node[]>([]);
  const edges = ref<Edge[]>([]);
  const selectedNode = ref<Node | null>(null);

  const workflow = ref<WorkflowDef | null>(null);
  const loading = ref(true);
  const saving = ref(false);
  const showMinimap = ref(true);
  const initialized = ref(false);

  const canUndo = computed(() => store.canUndo);
  const canRedo = computed(() => store.canRedo);

  let saveDebounceTimer: ReturnType<typeof setTimeout> | null = null;

  async function init() {
    loading.value = true;
    try {
      if (workflowId === 'new') {
        workflow.value = {
          id: '',
          name: '新建工作流',
          description: '',
          nodes: [],
          edges: [],
          global_params: null,
          is_published: false,
          version: 1,
          sort: 0,
          is_deleted: false,
        };
        nodes.value = createDefaultWorkflowNodes();
        edges.value = [];
        store.initWorkflow('', { nodes: nodes.value, edges: edges.value });
        initialized.value = true;
        return;
      }

      const def = await getWorkflowDefDetailApi(workflowId);
      workflow.value = def;

      if (def.nodes && def.nodes.length > 0) {
        nodes.value = def.nodes.map(toFlowNode);
        edges.value = def.edges.map(toFlowEdge);
      } else {
        nodes.value = createDefaultWorkflowNodes();
        edges.value = [];
      }

      store.initWorkflow(workflowId, { nodes: nodes.value, edges: edges.value });
      initialized.value = true;
    } catch {
      ElMessage.error('加载工作流失败');
    } finally {
      loading.value = false;
    }
  }

  async function save(): Promise<string | undefined> {
    saving.value = true;
    try {
      const flowNodes = nodes.value.map(fromFlowNode);
      const flowEdges = edges.value.map(fromFlowEdge);

      if (workflow.value?.id) {
        await updateWorkflowDefApi(workflow.value.id, {
          name: workflow.value.name,
          description: workflow.value.description,
          nodes: flowNodes,
          edges: flowEdges,
        });
        store.markAsSaved();
        return workflow.value.id;
      }
      return undefined;
    } catch {
      ElMessage.error('保存失败');
      return undefined;
    } finally {
      saving.value = false;
    }
  }

  async function _doSave() {
    if (!workflow.value?.id) return;
    saving.value = true;
    try {
      const flowNodes = nodes.value.map(fromFlowNode);
      const flowEdges = edges.value.map(fromFlowEdge);
      await updateWorkflowDefApi(workflow.value.id, {
        name: workflow.value.name,
        description: workflow.value.description,
        nodes: flowNodes,
        edges: flowEdges,
      });
      store.markAsSaved();
    } catch {
      // 静默保存失败忽略
    } finally {
      saving.value = false;
    }
  }

  watch(
    [nodes, edges],
    () => {
      if (!initialized.value) return;
      store.saveHistory({ nodes: nodes.value, edges: edges.value });
      if (saveDebounceTimer) clearTimeout(saveDebounceTimer);
      saveDebounceTimer = setTimeout(_doSave, 500);
    },
    { deep: true },
  );

  async function publish(publishFlag: boolean) {
    if (!workflow.value?.id) {
      ElMessage.warning('请先保存工作流');
      return;
    }
    try {
      await publishWorkflowDefApi(workflow.value.id, publishFlag);
      workflow.value.is_published = publishFlag;
      ElMessage.success(publishFlag ? '已发布' : '已取消发布');
    } catch {
      ElMessage.error('操作失败');
    }
  }

  async function run() {
    if (!workflow.value?.id) return;
    if (!workflow.value.is_published) {
      ElMessage.warning('请先发布工作流');
      return;
    }
    try {
      const inst = await runWorkflowApi(workflow.value.id);
      ElMessage.success(`工作流已启动，实例ID: ${inst.id}`);
    } catch {
      ElMessage.error('启动失败');
    }
  }

  function undo() {
    const state = store.undo();
    if (state) {
      nodes.value = state.nodes;
      edges.value = state.edges;
    }
  }

  function redo() {
    const state = store.redo();
    if (state) {
      nodes.value = state.nodes;
      edges.value = state.edges;
    }
  }

  let dropCounter = 0;

  function onDrop(event: DragEvent) {
    const type = event.dataTransfer?.getData('application/vnd-workflow-node');
    const meta = type ? getNodeMeta(type) : null;
    if (!meta) return;

    const canvas = (event.currentTarget as HTMLElement)?.closest('.workflow-editor__canvas');
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left - 100;
    const y = event.clientY - rect.top - 50;
    const newNode: Node = {
      id: `${type}-${nanoid(6)}`,
      type: 'workflow',
      position: { x: Math.max(0, x), y: Math.max(0, y) },
      data: {
        type,
        label: meta.label,
        params: { ...meta.defaultParams },
        status: '',
      },
    };
    nodes.value.push(newNode);
    dropCounter++;
  }

  function onConnect(connection: any) {
    if (!connection.source || !connection.target) return;
    const edgeId = `e-${connection.source}-${connection.target}`;
    const exists = edges.value.some((e) => e.id === edgeId);
    if (exists) return;
    edges.value.push({
      id: edgeId,
      source: connection.source,
      target: connection.target,
      type: 'smoothstep',
    });
  }

  function onNodeClick(node: Node) {
    const found = nodes.value.find((n) => n.id === node.id);
    selectedNode.value = found || node;
  }

  function onPaneClick() {
    selectedNode.value = null;
  }

  function updateNodeParams(nodeId: string, params: Record<string, any>) {
    const node = nodes.value.find((n) => n.id === nodeId);
    if (node) {
      node.data = { ...node.data, params };
    }
  }

  function updateWorkflowName(name: string) {
    if (workflow.value) {
      workflow.value.name = name;
    }
  }

  function addNodeAtCenter(type: string) {
    const meta = getNodeMeta(type);
    if (!meta) return;
    const newNode: Node = {
      id: `${type}-${nanoid(6)}`,
      type: 'workflow',
      position: DEFAULT_NODE_POSITION,
      data: {
        type,
        label: meta.label,
        params: { ...meta.defaultParams },
        status: '',
      },
    };
    nodes.value.push(newNode);
  }

  function deleteSelectedNode() {
    const node = selectedNode.value;
    if (!node) return;
    if (node.data?.type === '_start' || node.data?.type === '_end') return;
    nodes.value = nodes.value.filter((n) => n.id !== node.id);
    edges.value = edges.value.filter(
      (e) => e.source !== node.id && e.target !== node.id,
    );
    selectedNode.value = null;
  }

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === 'Delete' || event.key === 'Backspace') {
      const tag = event.target as HTMLElement;
      if (tag.tagName === 'INPUT' || tag.tagName === 'TEXTAREA' || tag.isContentEditable) return;
      deleteSelectedNode();
    }
  }

  onMounted(() => {
    document.addEventListener('keydown', onKeyDown);
  });

  onBeforeUnmount(() => {
    document.removeEventListener('keydown', onKeyDown);
    if (saveDebounceTimer) clearTimeout(saveDebounceTimer);
    store.cleanup();
  });

  return {
    nodes,
    edges,
    selectedNode,
    workflow,
    loading,
    saving,
    showMinimap,
    canUndo,
    canRedo,
    initialized,
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
  };
}
