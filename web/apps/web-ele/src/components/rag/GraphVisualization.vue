<script lang="ts" setup>
import type { GraphData, GraphNode } from '#/api/core/rag';
import type { LayoutType } from '#/composables/useGraphLayout';

import { computed, onMounted, onUnmounted, ref, watch } from 'vue';

import { ElButton } from 'element-plus';

import { useGraphChart } from '#/composables/useGraphChart';

import EntityLegend from './EntityLegend.vue';
import NodeDetailsPanel from './NodeDetailsPanel.vue';
import NodeSearchBar from './NodeSearchBar.vue';

const props = defineProps<{
  graphData: GraphData | null;
  layout?: LayoutType;
  loading?: boolean;
  isSampled?: boolean;
  fullGraphLoading?: boolean;
}>();

const emit = defineEmits<{
  nodeClick: [node: GraphNode];
  toggleFullGraph: [];
}>();

const containerRef = ref<HTMLElement | null>(null);
const selectedNode = ref<GraphNode | null>(null);
const colorVersion = ref(0);

const searchQuery = ref('');
const isSearchFocused = ref(false);
const showSearchResults = ref(false);
const selectedResultIndex = ref(0);

const filteredNodes = computed(() => {
  if (!searchQuery.value.trim()) return [];
  const query = searchQuery.value.toLowerCase();
  return (props.graphData?.nodes || [])
    .filter(
      (node) =>
        node.name.toLowerCase().includes(query) ||
        node.category.toLowerCase().includes(query),
    )
    .slice(0, 10);
});

function onChartEvent(eventType: string, data?: GraphNode) {
  if (eventType === 'node-click') {
    selectedNode.value = data as GraphNode;
    emit('nodeClick', data as GraphNode);
  } else if (eventType === 'background-click') {
    selectedNode.value = null;
  }
}

const chartEmit = (event: string, ...args: any[]) =>
  onChartEvent(event, ...args);

const {
  selectedType,
  updateChart,
  applyLayout,
  filterByCategory,
  resetView,
  handleResize,
  highlightNode,
} = useGraphChart(containerRef, chartEmit, props.layout);

function selectAndLocateNode(node: GraphNode) {
  selectedNode.value = node;
  highlightNode(node.name);
  emit('nodeClick', node);
}

function searchAndLocate() {
  if (filteredNodes.value.length > 0 && selectedResultIndex.value >= 0) {
    const node = filteredNodes.value[selectedResultIndex.value];
    if (node) {
      selectAndLocateNode(node);
      searchQuery.value = node.name;
      showSearchResults.value = false;
    }
  }
}

function filterByType(type: string) {
  filterByCategory(selectedType.value === type ? null : type);
}

function clearFilter() {
  filterByCategory(null);
}

const showSampledHint = computed(() => {
  const stats = props.graphData?.stats;
  if (!stats) return false;
  return stats.total_nodes > 300 || stats.displayed_nodes !== stats.total_nodes;
});
const displayedCount = computed(() => props.graphData?.stats.displayed_nodes ?? 0);
const totalCount = computed(() => props.graphData?.stats.total_nodes ?? 0);

watch(
  () => props.graphData,
  (data) => {
    if (data && data.nodes.length > 0) {
      colorVersion.value++;
      updateChart(data);
    }
  },
  { deep: true },
);

const debounceTimer = ref<ReturnType<typeof setTimeout> | null>(null);

watch(
  () => props.layout,
  (newLayout) => {
    if (debounceTimer.value) clearTimeout(debounceTimer.value);
    debounceTimer.value = setTimeout(() => {
      if (newLayout && props.graphData) {
        applyLayout(newLayout);
      }
    }, 300);
  },
);

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    selectedNode.value = null;
  }
}

onMounted(() => {
  window.addEventListener('resize', handleResize);
  window.addEventListener('keydown', onKeydown);
  if (props.graphData && props.graphData.nodes.length > 0) {
    colorVersion.value++;
    updateChart(props.graphData);
  }
});

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
  window.removeEventListener('keydown', onKeydown);
  if (debounceTimer.value) clearTimeout(debounceTimer.value);
});

defineExpose({
  resetView,
  updateColors: () => {
    colorVersion.value++;
    if (props.graphData) updateChart(props.graphData);
  },
  applyLayout: (layout: LayoutType) => applyLayout(layout),
});
</script>

<template>
  <div class="graph-visualization">
    <div class="graph-main">
      <div ref="containerRef" class="chart-container"></div>

      <div v-if="!graphData" class="empty-hint">
        请先选择知识库和已构建图谱的文件
      </div>

      <div class="top-left-panel">
        <slot></slot>
        <NodeSearchBar
          v-model:search-query="searchQuery"
          v-model:is-search-focused="isSearchFocused"
          v-model:show-search-results="showSearchResults"
          v-model:selected-result-index="selectedResultIndex"
          :filtered-nodes="filteredNodes"
          @node-select="selectAndLocateNode"
          @search-and-locate="searchAndLocate"
        />
      </div>

      <NodeDetailsPanel :node="selectedNode" @close="selectedNode = null" />

      <EntityLegend
        :nodes="graphData?.nodes || []"
        :selected-type="selectedType"
        :color-version="colorVersion"
        :stats-nodes="graphData?.stats.displayed_nodes ?? graphData?.stats.total_nodes ?? 0"
        :edges="graphData?.stats.displayed_edges ?? graphData?.stats.total_edges ?? 0"
        @type-click="filterByType"
        @clear-filter="clearFilter"
      />

      <div v-if="showSampledHint" class="graph-hint-bar">
        <span class="hint-text">
          图谱数据量较大，当前显示
          <strong>{{ displayedCount }}</strong>
          个核心节点
          <template v-if="totalCount > displayedCount">
            （共 {{ totalCount }} 节点）
          </template>
        </span>
        <ElButton
          size="small"
          type="primary"
          plain
          :loading="fullGraphLoading"
          @click="$emit('toggleFullGraph')"
        >
          {{ isSampled ? '查看全量图谱' : '显示采样图谱' }}
        </ElButton>
      </div>
    </div>
  </div>
</template>

<style scoped>
.graph-visualization {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.graph-main {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.chart-container {
  width: 100%;
  height: 100%;
}

.empty-hint {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 50;
  font-size: 16px;
  color: var(--el-text-color-secondary);
  transform: translate(-50%, -50%);
}

.top-left-panel {
  position: absolute;
  top: 12px;
  left: 16px;
  z-index: 100;
  display: flex;
  gap: 8px;
  align-items: center;
}

.graph-hint-bar {
  position: absolute;
  bottom: 20px;
  left: 50%;
  z-index: 100;
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 10px 20px;
  font-size: 13px;
  color: #1a1a2e;
  background: rgb(255 255 255 / 95%);
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgb(0 0 0 / 10%);
  transform: translateX(-50%);
  backdrop-filter: blur(10px);
  white-space: nowrap;
}
</style>
