<script setup lang="ts">
import type { TeamConfig } from '#/api/core/ai-workflow';

import { ref, watch } from 'vue';

import {
  ElButton,
  ElDialog,
  ElInput,
  ElMessage,
} from 'element-plus';

import { requestClient } from '#/api/request';

const props = defineProps<{
  modelValue: boolean;
  team: TeamConfig | null;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void;
}>();

const visible = ref(false);
const inputText = ref('');
const running = ref(false);
const logs = ref<{ time: string; text: string; type: string }[]>([]);
const result = ref('');
const error = ref('');

let controller: AbortController | null = null;

const EVENT_ICONS: Record<string, string> = {
  team_start: '🚀',
  team_role_start: '🤖',
  team_handoff: '🔄',
  team_role_complete: '✅',
  workflow_complete: '🎉',
  workflow_error: '❌',
};

function getTime(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
}

function handleEvent(event: { event: string; data: string }) {
  let text = event.event;

  try {
    const data = JSON.parse(event.data);

    switch (event.event) {
      case 'team_start':
        text = `团队 "${data.team_name}" 开始工作`;
        break;
      case 'team_role_start':
        text = `${data.role} 开始第${data.step}步`;
        logs.value = []; // 清空旧日志
        break;
      case 'team_handoff':
        text = `${data.from_role} → ${data.to_role}`;
        break;
      case 'team_role_complete':
        text = `${data.role} 完成`;
        break;
      case 'workflow_complete':
        text = '团队完成！';
        if (data.result) {
          result.value = data.result;
        }
        break;
      case 'workflow_error':
        text = '运行出错';
        error.value = data.message || '未知错误';
        break;
      default:
        text = `${event.event}: ${JSON.stringify(data)}`;
    }
  } catch {
    text = event.data || event.event;
  }

  logs.value.push({ time: getTime(), text, type: event.event });
}

function handleError(err: Error) {
  error.value = err.message || '连接失败';
  logs.value.push({ time: getTime(), text: `错误: ${error.value}`, type: 'error' });
}

function handleComplete() {
  running.value = false;
  controller = null;
}

watch(
  () => props.modelValue,
  (val) => {
    visible.value = val;
    if (val) {
      inputText.value = '';
      logs.value = [];
      result.value = '';
      error.value = '';
      running.value = false;
      controller = null;
    }
  },
);

watch(visible, (val) => {
  emit('update:modelValue', val);
});

function startRun() {
  if (!props.team) return;
  if (!inputText.value.trim()) {
    ElMessage.warning('请输入问题');
    return;
  }

  running.value = true;
  logs.value = [];
  result.value = '';
  error.value = '';

  controller = new AbortController();

  requestClient
    .postSSE(
      `/api/ai-workflow/teams/${props.team.id}/stream`,
      { input_params: { input: inputText.value } },
      {
        signal: controller.signal,
        onMessage(content: string) {
          const lines = content.split('\n');
          for (const line of lines) {
            if (line.startsWith('data: [DONE]')) {
              handleComplete();
              return;
            }
            if (line.startsWith('data: ')) {
              try {
                const parsed = JSON.parse(line.slice(6));
                handleEvent(parsed);
                if (parsed.event === 'workflow_complete' || parsed.event === 'workflow_error') {
                  running.value = false;
                }
              } catch {
                // ignore
              }
            }
          }
        },
        onEnd() {
          handleComplete();
        },
      },
    )
    .catch((err: Error) => {
      if (err.name !== 'AbortError') {
        handleError(err);
      }
      running.value = false;
    });
}

function stopRun() {
  if (controller) {
    controller.abort();
    controller = null;
  }
  running.value = false;
}
</script>

<template>
  <ElDialog
    :model-value="visible"
    :title="team ? `运行: ${team.name}` : '运行团队'"
    width="680px"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="run-dialog">
      <!-- 输入区 -->
      <div class="input-section">
        <label class="input-label">输入问题</label>
        <ElInput
          v-model="inputText"
          type="textarea"
          :rows="2"
          placeholder="输入问题或任务描述..."
          :disabled="running"
        />
      </div>

      <!-- 控制按钮 -->
      <div class="control-section">
        <ElButton
          v-if="!running"
          type="primary"
          :disabled="!inputText.trim() || !team"
          @click="startRun"
        >
          ▶ 开始运行
        </ElButton>
        <ElButton
          v-else
          type="danger"
          @click="stopRun"
        >
          ⏹ 停止
        </ElButton>
      </div>

      <!-- 日志区 -->
      <div v-if="logs.length > 0" class="logs-section">
        <div class="logs-header">执行日志</div>
        <div class="logs-body">
          <div
            v-for="(log, i) in logs"
            :key="i"
            class="log-line"
            :class="{ 'log-line--error': log.type === 'workflow_error' || log.type === 'error', 'log-line--success': log.type === 'workflow_complete' }"
          >
            <span class="log-time">{{ log.time }}</span>
            <span class="log-icon">{{ EVENT_ICONS[log.type] || '•' }}</span>
            <span class="log-text">{{ log.text }}</span>
          </div>
        </div>
      </div>

      <!-- 结果区 -->
      <div v-if="result" class="result-section">
        <div class="result-header">最终结果</div>
        <div class="result-body">{{ result }}</div>
      </div>

      <!-- 错误区 -->
      <div v-if="error" class="error-section">
        <div class="result-header" style="color: var(--el-color-danger)">错误信息</div>
        <div class="error-body">{{ error }}</div>
      </div>
    </div>

    <template #footer>
      <ElButton @click="visible = false">关闭</ElButton>
    </template>
  </ElDialog>
</template>

<style scoped>
.run-dialog {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.input-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.input-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.control-section {
  display: flex;
  gap: 8px;
}

.logs-section {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}

.logs-header {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.logs-body {
  max-height: 280px;
  overflow-y: auto;
  padding: 8px 12px;
  background: var(--el-bg-color);
}

.log-line {
  display: flex;
  gap: 6px;
  align-items: flex-start;
  padding: 3px 0;
  font-size: 12px;
  line-height: 1.5;
  font-family: 'SF Mono', 'Consolas', monospace;
}

.log-time {
  color: var(--el-text-color-placeholder);
  flex-shrink: 0;
  width: 64px;
}

.log-icon {
  flex-shrink: 0;
  width: 16px;
  text-align: center;
}

.log-text {
  color: var(--el-text-color-primary);
  word-break: break-all;
}

.log-line--error .log-text {
  color: var(--el-color-danger);
}

.log-line--success .log-text {
  color: var(--el-color-success);
}

.result-section {
  border: 1px solid var(--el-color-success-light-5);
  border-radius: 8px;
  overflow: hidden;
}

.result-header {
  font-size: 12px;
  font-weight: 600;
  padding: 8px 12px;
  background: var(--el-color-success-light-9);
  border-bottom: 1px solid var(--el-color-success-light-5);
}

.result-body {
  padding: 12px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--el-bg-color);
  max-height: 200px;
  overflow-y: auto;
}

.error-section {
  border: 1px solid var(--el-color-danger-light-5);
  border-radius: 8px;
  overflow: hidden;
}

.error-body {
  padding: 12px;
  font-size: 13px;
  color: var(--el-color-danger);
  background: var(--el-bg-color);
  white-space: pre-wrap;
}
</style>
