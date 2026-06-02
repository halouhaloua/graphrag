<script lang="ts" setup>
import type { GraphData, KnowledgeBaseFile } from '#/api/core/rag';
import type { LayoutType } from '#/composables/useGraphLayout';

import { computed, ref, watch } from 'vue';

import { ElMessage } from 'element-plus';

import { getGraphDataApi } from '#/api/core/rag';
import GraphToolbar from '#/components/rag/GraphToolbar.vue';
import GraphVisualization from '#/components/rag/GraphVisualization.vue';

const props = defineProps<{
  files: KnowledgeBaseFile[];
  kbId: string;
  selectedFileId: string;
}>();

const graphData = ref<GraphData | null>(null);
const loading = ref(false);
const currentLayout = ref<LayoutType>('static-force');
const isFullGraph = ref(false);
const fullGraphLoading = ref(false);

const isSampled = computed(() => {
  const stats = graphData.value?.stats;
  return !isFullGraph.value && !!stats && stats.total_nodes > 300;
});

const selectedFileName = computed(
  () => props.files.find((f) => f.id === props.selectedFileId)?.filename || '',
);

async function loadGraph(fileId: string, maxNodes?: number) {
  if (!fileId) return;
  loading.value = true;
  try {
    const res = await getGraphDataApi(props.kbId, fileId, maxNodes);
    graphData.value = res;
  } catch (error: any) {
    ElMessage.error(error.message || '加载图谱失败');
    graphData.value = null;
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.selectedFileId,
  (fileId) => {
    if (fileId) {
      isFullGraph.value = false;
      loadGraph(fileId, 500);
    }
  },
  { immediate: true },
);

function onRefresh() {
  if (props.selectedFileId) {
    isFullGraph.value = false;
    loadGraph(props.selectedFileId, 500);
  }
}

async function handleToggleFullGraph() {
  if (!props.selectedFileId) return;
  fullGraphLoading.value = true;
  try {
    const maxNodes = isFullGraph.value ? 500 : 0;
    const res = await getGraphDataApi(props.kbId, props.selectedFileId, maxNodes);
    graphData.value = res;
    isFullGraph.value = !isFullGraph.value;
  } catch (error: any) {
    ElMessage.error(error.message || '切换图谱模式失败');
  } finally {
    fullGraphLoading.value = false;
  }
}

function onLayoutChange(layout: LayoutType) {
  currentLayout.value = layout;
}

const graphVizRef = ref<InstanceType<typeof GraphVisualization> | null>(null);

function onReset() {
  graphVizRef.value?.resetView();
}

function onColorSchemeChange() {
  graphVizRef.value?.updateColors();
}
</script>

<template>
  <div class="graph-tab">
    <div class="graph-wrapper">
      <GraphToolbar
        :current-layout="currentLayout"
        :file-label="selectedFileName"
        :loading="loading"
        @refresh="onRefresh"
        @reset="onReset"
        @color-scheme-change="onColorSchemeChange"
        @layout-change="onLayoutChange"
      />
      <GraphVisualization
        ref="graphVizRef"
        :graph-data="graphData"
        :loading="loading"
        :layout="currentLayout"
        :is-sampled="isSampled"
        :full-graph-loading="fullGraphLoading"
        @toggle-full-graph="handleToggleFullGraph"
      />
    </div>
  </div>
</template>

<style scoped>
.graph-tab {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.graph-wrapper {
  position: relative;
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
</style>
