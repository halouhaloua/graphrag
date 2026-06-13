<script setup lang="ts">
import type { Node } from '@vue-flow/core';
import { computed, nextTick, onMounted, ref } from 'vue';

import { IconifyIcon, Trash2 } from '@vben/icons';
import {
  ElButton,
  ElCheckbox,
  ElCheckboxGroup,
  ElInput,
  ElInputNumber,
  ElOption,
  ElSelect,
  ElSlider,
  ElTag,
} from 'element-plus';

import { getNodeMeta, NODE_TYPE_MAP } from '../nodes/index';

const availableTools = computed(() => {
  return Object.values(NODE_TYPE_MAP).filter(
    (n) => n.type && !['_start', '_end', 'chat', 'condition'].includes(n.type),
  );
});

const props = defineProps<{
  selectedNode: Node | null;
}>();

const emit = defineEmits<{
  updateParams: [nodeId: string, params: Record<string, any>];
  deleteNode: [nodeId: string];
  close: [];
}>();

const visible = ref(false);

onMounted(() => {
  nextTick(() => {
    visible.value = true;
  });
});

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

function updateJsonParam(key: string, raw: string) {
  try {
    const parsed = JSON.parse(raw);
    updateParam(key, parsed);
  } catch {
    // ignore parse errors until input stabilizes
  }
}
</script>

<template>
  <div class="config-card" :class="{ 'is-visible': visible }">
    <div class="config-card__header">
      <div v-if="meta" class="config-card__header-left">
        <div class="config-card__icon" :style="{ background: meta.color }">
          <IconifyIcon :icon="`lucide:${meta.icon}`" class="h-4 w-4 text-white" />
        </div>
        <div class="config-card__title-area">
          <div class="config-card__title">{{ selectedNode?.data?.label || meta?.label }}</div>
          <div class="config-card__type">{{ meta?.label }}</div>
        </div>
      </div>
      <ElButton text size="small" class="config-card__close" @click="emit('close')">
        <IconifyIcon icon="lucide:x" class="h-4 w-4" />
      </ElButton>
    </div>

    <div class="config-card__body">
      <div class="cfg-section">
        <div class="cfg-section__label">节点名称</div>
        <ElInput
          :model-value="selectedNode?.data?.label"
          size="small"
          placeholder="请输入节点名称"
          @update:model-value="selectedNode!.data!.label = $event"
        />
      </div>

      <template v-if="meta?.type === 'chat'">
        <div class="cfg-section">
          <div class="cfg-section__label">系统提示词</div>
          <ElInput
            :model-value="localParams.system_prompt"
            type="textarea"
            :rows="3"
            size="small"
            placeholder="可选，设置LLM的角色和行为"
            @update:model-value="updateParam('system_prompt', $event)"
          />
        </div>
        <div class="cfg-section">
          <div class="cfg-section__label">用户问题</div>
          <ElInput
            :model-value="localParams.user_question"
            type="textarea"
            :rows="4"
            size="small"
            placeholder="输入用户问题，支持 ${nodeId.key} 引用上游输出"
            @update:model-value="updateParam('user_question', $event)"
          />
        </div>
        <div class="cfg-section">
          <div class="cfg-section__label-row">
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
        <div class="cfg-section">
          <div class="cfg-section__label">可用工具</div>
          <ElCheckboxGroup
            :model-value="localParams.tools || []"
            @update:model-value="updateParam('tools', $event)"
          >
            <div v-for="t in availableTools" :key="t.type" class="tool-check-item">
              <ElCheckbox :label="t.type" :value="t.type">
                {{ t.label }}
              </ElCheckbox>
            </div>
          </ElCheckboxGroup>
          <div v-if="availableTools.length === 0" class="tool-empty">暂无可用工具</div>
        </div>
        <div class="cfg-section">
          <div class="cfg-section__label">最大工具轮数</div>
          <ElInputNumber
            :model-value="localParams.max_tool_rounds ?? 10"
            :min="1"
            :max="50"
            size="small"
            :style="{ width: '100%' }"
            @update:model-value="updateParam('max_tool_rounds', $event)"
          />
        </div>
      </template>

      <template v-else-if="meta?.type === 'serper_search'">
        <div class="cfg-section">
          <div class="cfg-section__label">搜索关键词</div>
          <ElInput
            :model-value="localParams.query"
            size="small"
            placeholder="输入搜索关键词"
            @update:model-value="updateParam('query', $event)"
          />
        </div>
        <div class="cfg-section">
          <div class="cfg-section__label">最大结果数</div>
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

      <template v-else-if="meta?.type === 'web_crawler'">
        <div class="cfg-section">
          <div class="cfg-section__label">目标URL</div>
          <ElInput
            :model-value="localParams.url"
            size="small"
            placeholder="https://example.com"
            @update:model-value="updateParam('url', $event)"
          />
        </div>
      </template>

      <template v-else-if="meta?.type === 'api_call'">
        <div class="cfg-section">
          <div class="cfg-section__label">请求方法</div>
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
        <div class="cfg-section">
          <div class="cfg-section__label">API地址</div>
          <ElInput
            :model-value="localParams.url"
            size="small"
            placeholder="https://api.example.com/endpoint"
            @update:model-value="updateParam('url', $event)"
          />
        </div>
        <div class="cfg-section">
          <div class="cfg-section__label">Bearer Token</div>
          <ElInput
            :model-value="localParams.bearer_token"
            size="small"
            placeholder="可选"
            @update:model-value="updateParam('bearer_token', $event)"
          />
        </div>
      </template>

      <template v-else-if="meta?.type === 'python_execute'">
        <div class="cfg-section">
          <div class="cfg-section__label">代码语言</div>
          <ElSelect
            :model-value="localParams.language || 'python'"
            size="small"
            @update:model-value="updateParam('language', $event)"
          >
            <ElOption label="Python" value="python" />
            <ElOption label="Shell" value="shell" />
          </ElSelect>
        </div>
        <div class="cfg-section">
          <div class="cfg-section__label">代码</div>
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

      <template v-else-if="meta?.type === 'browser_agent'">
        <div class="cfg-section">
          <div class="cfg-section__label">浏览器任务描述</div>
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

      <template v-else-if="meta?.type === 'weather_forecast'">
        <div class="cfg-section">
          <div class="cfg-section__label">纬度</div>
          <ElInput
            :model-value="localParams.latitude"
            type="number"
            size="small"
            placeholder="39.9042"
            @update:model-value="updateParam('latitude', Number($event))"
          />
        </div>
        <div class="cfg-section">
          <div class="cfg-section__label">经度</div>
          <ElInput
            :model-value="localParams.longitude"
            type="number"
            size="small"
            placeholder="116.4074"
            @update:model-value="updateParam('longitude', Number($event))"
          />
        </div>
      </template>

      <template v-else-if="meta?.type === 'arxiv_search'">
        <div class="cfg-section">
          <div class="cfg-section__label">搜索关键词</div>
          <ElInput
            :model-value="localParams.query"
            size="small"
            placeholder="machine learning"
            @update:model-value="updateParam('query', $event)"
          />
        </div>
        <div class="cfg-section">
          <div class="cfg-section__label">最大结果数</div>
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

      <template v-else-if="meta?.type === '_start'">
        <div class="cfg-section">
          <div class="cfg-section__label">用户输入提示</div>
          <ElInput
            :model-value="localParams.user_input_description"
            size="small"
            placeholder="例如：请输入您的问题"
            @update:model-value="updateParam('user_input_description', $event)"
          />
          <div class="cfg-section__hint">
            此提示将在工作流运行页面的输入框中显示，不填则不显示。
          </div>
        </div>
      </template>
      <template v-else-if="meta?.type === '_end'">
        <div class="cfg-empty">此节点无可配置参数</div>
      </template>

      <template v-else-if="meta?.type === 'rag_query'">
        <div class="cfg-section">
          <div class="cfg-section__label">知识库ID</div>
          <ElInput
            :model-value="localParams.kb_id"
            size="small"
            placeholder="请输入知识库ID"
            @update:model-value="updateParam('kb_id', $event)"
          />
        </div>
        <div class="cfg-section">
          <div class="cfg-section__label">文件ID（可选）</div>
          <ElInput
            :model-value="localParams.file_id"
            size="small"
            placeholder="不填时自动选择有图谱的文件"
            @update:model-value="updateParam('file_id', $event)"
          />
          <div class="cfg-section__hint">指定知识库中的特定文件</div>
        </div>
        <div class="cfg-section">
          <div class="cfg-section__label">问题</div>
          <ElInput
            :model-value="localParams.question"
            type="textarea"
            :rows="4"
            size="small"
            placeholder="基于知识库提问，支持 ${node.key} 引用上游"
            @update:model-value="updateParam('question', $event)"
          />
        </div>
        <div class="cfg-section">
          <div class="cfg-section__label-row">
            <span>IRCoT 迭代检索</span>
          </div>
          <ElSelect
            :model-value="localParams.enable_ircot ? 'true' : 'false'"
            size="small"
            @update:model-value="updateParam('enable_ircot', $event === 'true')"
          >
            <ElOption label="关闭（直接回答）" value="false" />
            <ElOption label="开启（迭代检索+推理）" value="true" />
          </ElSelect>
          <div class="cfg-section__hint">开启后 LLM 可多轮检索，适用于复杂问题</div>
        </div>
        <div class="cfg-section">
          <div class="cfg-section__label">检索返回数量</div>
          <ElInputNumber
            :model-value="localParams.top_k ?? 10"
            :min="1"
            :max="100"
            size="small"
            :style="{ width: '100%' }"
            @update:model-value="updateParam('top_k', $event)"
          />
        </div>
      </template>

      <template v-else-if="meta?.type === 'db_query'">
        <div class="cfg-section">
          <div class="cfg-section__label">SQL 查询</div>
          <ElInput
            :model-value="localParams.sql"
            type="textarea"
            :rows="4"
            size="small"
            placeholder="SELECT * FROM table WHERE id = :id"
            @update:model-value="updateParam('sql', $event)"
          />
          <div class="cfg-section__hint">仅支持 SELECT / WITH 等只读查询，使用 :key 传参</div>
        </div>
        <div class="cfg-section">
          <div class="cfg-section__label">参数 (JSON)</div>
          <ElInput
            :model-value="typeof localParams.params === 'object' ? JSON.stringify(localParams.params, null, 2) : localParams.params"
            type="textarea"
            :rows="3"
            size="small"
            placeholder='{"id": 1}'
            @update:model-value="updateJsonParam('params', $event)"
          />
        </div>
        <div class="cfg-section">
          <div class="cfg-section__label">最大行数</div>
          <ElInputNumber
            :model-value="localParams.max_rows ?? 100"
            :min="1"
            :max="1000"
            size="small"
            :style="{ width: '100%' }"
            @update:model-value="updateParam('max_rows', $event)"
          />
        </div>
      </template>

      <template v-else-if="meta?.type === 'condition'">
        <div class="cfg-section">
          <div class="cfg-section__label">左值</div>
          <ElInput
            :model-value="localParams.left"
            size="small"
            placeholder='${node_id.result} 或直接输入值'
            @update:model-value="updateParam('left', $event)"
          />
        </div>
        <div class="cfg-section">
          <div class="cfg-section__label">运算符</div>
          <ElSelect
            :model-value="localParams.operator || 'equals'"
            size="small"
            @update:model-value="updateParam('operator', $event)"
          >
            <ElOption label="等于 (equals)" value="equals" />
            <ElOption label="不等于 (not_equals)" value="not_equals" />
            <ElOption label="包含 (contains)" value="contains" />
            <ElOption label="大于 (gt)" value="gt" />
            <ElOption label="大于等于 (gte)" value="gte" />
            <ElOption label="小于 (lt)" value="lt" />
            <ElOption label="小于等于 (lte)" value="lte" />
            <ElOption label="为空 (is_empty)" value="is_empty" />
            <ElOption label="不为空 (is_not_empty)" value="is_not_empty" />
            <ElOption label="开头是 (starts_with)" value="starts_with" />
            <ElOption label="结尾是 (ends_with)" value="ends_with" />
          </ElSelect>
        </div>
        <div class="cfg-section">
          <div class="cfg-section__label">右值</div>
          <ElInput
            :model-value="localParams.right"
            size="small"
            placeholder="is_empty / is_not_empty 时可不填"
            @update:model-value="updateParam('right', $event)"
          />
        </div>
      </template>

      <template v-else>
        <div class="cfg-empty">此节点无可配置参数</div>
      </template>

      <div
        v-if="meta?.type !== '_start' && meta?.type !== '_end'"
        class="cfg-delete"
      >
        <ElButton
          type="danger"
          size="small"
          plain
          class="!w-full"
          @click="emit('deleteNode', props.selectedNode!.id)"
        >
          <Trash2 class="mr-1 h-3.5 w-3.5" />
          删除节点
        </ElButton>
      </div>
    </div>
  </div>
</template>

<style scoped>
.config-card {
  position: absolute;
  top: 10vh;
  right: 24px;
  width: 320px;
  max-height: 80vh;
  z-index: 15;
  background: #fff;
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  overflow-y: auto;
  opacity: 0;
  transform: translateY(-8px) scale(0.97);
  transition: opacity 0.2s ease, transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.config-card.is-visible {
  opacity: 1;
  transform: translateY(0) scale(1);
}

.config-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 16px 16px 12px;
  border-bottom: 1px solid #f1f5f9;
}
.config-card__header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}
.config-card__icon {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.config-card__title-area {
  min-width: 0;
}
.config-card__title {
  font-weight: 600;
  font-size: 14px;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.config-card__type {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 1px;
}
.config-card__close {
  width: 28px;
  height: 28px;
  padding: 0;
  color: #94a3b8;
  flex-shrink: 0;
  border-radius: 6px;
}
.config-card__close:hover {
  color: #1e293b;
  background: #f1f5f9;
}

.config-card__body {
  padding: 16px;
}
.cfg-section {
  margin-bottom: 16px;
}
.cfg-section__label {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 6px;
}
.cfg-section__label-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 6px;
}
.cfg-empty {
  text-align: center;
  color: #94a3b8;
  font-size: 12px;
  padding: 20px 0;
}

.cfg-section__hint {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 4px;
  line-height: 1.4;
}
.cfg-delete {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
}

/* ElInput / ElSelect / ElSlider 圆角美化 */
.config-card__body :deep(.el-input__wrapper) {
  border-radius: 8px;
}
.config-card__body :deep(.el-select) {
  width: 100%;
}
.config-card__body :deep(.el-textarea__inner) {
  border-radius: 8px;
}
.tool-check-item {
  padding: 3px 0;
}
.tool-empty {
  font-size: 12px;
  color: #94a3b8;
  padding: 4px 0;
}
</style>
