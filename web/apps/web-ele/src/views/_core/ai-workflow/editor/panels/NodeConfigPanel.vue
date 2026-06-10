<script setup lang="ts">
import type { Node } from '@vue-flow/core';
import { computed } from 'vue';

import { IconifyIcon } from '@vben/icons';
import {
  ElInput,
  ElOption,
  ElSelect,
  ElSlider,
  ElTag,
} from 'element-plus';

import { getNodeMeta } from '../nodes/index';

const props = defineProps<{
  selectedNode: Node | null;
}>();

const emit = defineEmits<{
  updateParams: [nodeId: string, params: Record<string, any>];
}>();

const meta = computed(() => {
  if (!props.selectedNode?.data?.type) return null;
  return getNodeMeta(props.selectedNode.data.type);
});

const localParams = computed(() => {
  return props.selectedNode?.data?.params || {};
});

function updateParam(key: string, value: any) {
  if (!props.selectedNode) return;
  const newParams = { ...localParams.value, [key]: value };
  emit('updateParams', props.selectedNode.id, newParams);
}
</script>

<template>
  <aside class="node-config-panel" :class="{ 'is-empty': !selectedNode }">
    <template v-if="selectedNode && meta">
      <div class="panel-header">
        <div class="panel-header__icon" :style="{ background: meta.color }">
          <IconifyIcon :icon="`lucide:${meta.icon}`" class="h-4 w-4 text-white" />
        </div>
        <div class="panel-header__info">
          <div class="panel-header__title">{{ selectedNode.data?.label || meta.label }}</div>
          <div class="panel-header__type">{{ meta.label }}</div>
        </div>
      </div>

      <div class="panel-body">
        <div class="config-section">
          <div class="config-section__title">节点名称</div>
          <ElInput
            :model-value="selectedNode.data?.label"
            size="small"
            placeholder="请输入节点名称"
            @update:model-value="selectedNode.data!.label = $event"
          />
        </div>

        <template v-if="meta.type === 'chat'">
          <div class="config-section">
            <div class="config-section__title">系统提示词</div>
            <ElInput
              :model-value="localParams.system_prompt"
              type="textarea"
              :rows="3"
              size="small"
              placeholder="可选，设置LLM的角色和行为"
              @update:model-value="updateParam('system_prompt', $event)"
            />
          </div>
          <div class="config-section">
            <div class="config-section__title">用户问题</div>
            <ElInput
              :model-value="localParams.user_question"
              type="textarea"
              :rows="4"
              size="small"
              placeholder="输入用户问题，支持 ${nodeId.key} 引用上游输出"
              @update:model-value="updateParam('user_question', $event)"
            />
          </div>
          <div class="config-section">
            <div class="config-section__title">
              <span>温度</span>
              <ElTag size="small" type="info">{{ localParams.temperature ?? 0.7 }}</ElTag>
            </div>
            <ElSlider
              :model-value="localParams.temperature ?? 0.7"
              :min="0"
              :max="2"
              :step="0.1"
              @update:model-value="updateParam('temperature', $event)"
            />
          </div>
        </template>

        <template v-else-if="meta.type === 'serper_search'">
          <div class="config-section">
            <div class="config-section__title">搜索关键词</div>
            <ElInput
              :model-value="localParams.query"
              size="small"
              placeholder="输入搜索关键词"
              @update:model-value="updateParam('query', $event)"
            />
          </div>
          <div class="config-section">
            <div class="config-section__title">最大结果数</div>
            <ElInput
              :model-value="localParams.max_results ?? 10"
              type="number"
              size="small"
              :min="1"
              :max="50"
              @update:model-value="updateParam('max_results', Number($event))"
            />
          </div>
        </template>

        <template v-else-if="meta.type === 'web_crawler'">
          <div class="config-section">
            <div class="config-section__title">目标URL</div>
            <ElInput
              :model-value="localParams.url"
              size="small"
              placeholder="https://example.com"
              @update:model-value="updateParam('url', $event)"
            />
          </div>
        </template>

        <template v-else-if="meta.type === 'api_call'">
          <div class="config-section">
            <div class="config-section__title">请求方法</div>
            <ElSelect
              :model-value="localParams.method || 'GET'"
              size="small"
              @update:model-value="updateParam('method', $event)"
            >
              <ElOption label="GET" value="GET" />
              <ElOption label="POST" value="POST" />
              <ElOption label="PUT" value="PUT" />
              <ElOption label="DELETE" value="DELETE" />
            </ElSelect>
          </div>
          <div class="config-section">
            <div class="config-section__title">API地址</div>
            <ElInput
              :model-value="localParams.url"
              size="small"
              placeholder="https://api.example.com/endpoint"
              @update:model-value="updateParam('url', $event)"
            />
          </div>
          <div class="config-section">
            <div class="config-section__title">Bearer Token</div>
            <ElInput
              :model-value="localParams.bearer_token"
              size="small"
              placeholder="可选"
              @update:model-value="updateParam('bearer_token', $event)"
            />
          </div>
        </template>

        <template v-else-if="meta.type === 'python_execute'">
          <div class="config-section">
            <div class="config-section__title">代码语言</div>
            <ElSelect
              :model-value="localParams.language || 'python'"
              size="small"
              @update:model-value="updateParam('language', $event)"
            >
              <ElOption label="Python" value="python" />
              <ElOption label="Shell" value="shell" />
            </ElSelect>
          </div>
          <div class="config-section">
            <div class="config-section__title">代码</div>
            <ElInput
              :model-value="localParams.code"
              type="textarea"
              :rows="6"
              size="small"
              placeholder="print('Hello World')"
              @update:model-value="updateParam('code', $event)"
            />
          </div>
        </template>

        <template v-else-if="meta.type === 'browser_agent'">
          <div class="config-section">
            <div class="config-section__title">浏览器任务描述</div>
            <ElInput
              :model-value="localParams.task"
              type="textarea"
              :rows="4"
              size="small"
              placeholder="例如：打开百度，搜索'人工智能'"
              @update:model-value="updateParam('task', $event)"
            />
          </div>
        </template>

        <template v-else-if="meta.type === 'weather_forecast'">
          <div class="config-section">
            <div class="config-section__title">纬度</div>
            <ElInput
              :model-value="localParams.latitude"
              type="number"
              size="small"
              placeholder="39.9042"
              @update:model-value="updateParam('latitude', Number($event))"
            />
          </div>
          <div class="config-section">
            <div class="config-section__title">经度</div>
            <ElInput
              :model-value="localParams.longitude"
              type="number"
              size="small"
              placeholder="116.4074"
              @update:model-value="updateParam('longitude', Number($event))"
            />
          </div>
        </template>

        <template v-else-if="meta.type === 'arxiv_search'">
          <div class="config-section">
            <div class="config-section__title">搜索关键词</div>
            <ElInput
              :model-value="localParams.query"
              size="small"
              placeholder="machine learning"
              @update:model-value="updateParam('query', $event)"
            />
          </div>
          <div class="config-section">
            <div class="config-section__title">最大结果数</div>
            <ElInput
              :model-value="localParams.max_results ?? 5"
              type="number"
              size="small"
              :min="1"
              :max="50"
              @update:model-value="updateParam('max_results', Number($event))"
            />
          </div>
        </template>

        <template v-else-if="meta.type === '_start' || meta.type === '_end'">
          <div class="config-empty">流程控制节点，无需配置参数</div>
        </template>

        <template v-else>
          <div class="config-empty">此节点无可配置参数</div>
        </template>
      </div>
    </template>

    <template v-else>
      <div class="panel-empty-state">
        <IconifyIcon icon="lucide:mouse-pointer-click" class="panel-empty-icon" />
        <p>点击左侧画布中的节点</p>
        <p>查看和配置参数</p>
      </div>
    </template>
  </aside>
</template>

<style scoped>
.node-config-panel {
  width: 280px;
  background: #fff;
  border-left: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow-y: auto;
}
.node-config-panel.is-empty {
  justify-content: center;
  align-items: center;
}
.panel-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px;
  border-bottom: 1px solid #f1f5f9;
}
.panel-header__icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.panel-header__title {
  font-weight: 600;
  font-size: 14px;
  color: #1e293b;
}
.panel-header__type {
  font-size: 11px;
  color: #94a3b8;
}
.panel-body {
  padding: 12px 14px;
  flex: 1;
}
.config-section {
  margin-bottom: 14px;
}
.config-section__title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  color: #475569;
  margin-bottom: 6px;
}
.config-empty {
  text-align: center;
  color: #94a3b8;
  font-size: 12px;
  padding: 20px 0;
}
.panel-empty-state {
  text-align: center;
  color: #94a3b8;
  padding: 20px;
}
.panel-empty-icon {
  width: 40px;
  height: 40px;
  margin-bottom: 12px;
  opacity: 0.5;
}
.panel-empty-state p {
  font-size: 12px;
  margin: 2px 0;
}
</style>
