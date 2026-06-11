<script setup lang="ts">
import type { TeamConfig, TeamRoleDef } from '#/api/core/ai-workflow';

import {
  computed,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue';
import { useRoute, useRouter } from 'vue-router';

import {
  ArrowLeft,
  Copy,
  Download,
  Play,
  Plus,
  Save,
  Trash2,
  X,
} from '@vben/icons';

import {
  ElButton,
  ElCheckbox,
  ElCheckboxGroup,
  ElEmpty,
  ElInput,
  ElInputNumber,
  ElMessage,
  ElMessageBox,
  ElOption,
  ElSelect,
  ElTabPane,
  ElTabs,
  ElTag,
  ElTooltip,
} from 'element-plus';

import {
  getTeamDetailApi,
  createTeamApi,
  updateTeamApi,
} from '#/api/core/ai-workflow';
import { requestClient } from '#/api/request';
import { NODE_TYPE_MAP } from '../editor/nodes/index';

defineOptions({ name: 'AiWorkflowTeamDetail' });

interface RoleFormItem {
  key: string;
  agentDescription: string;
  modelName: string;
  maxIterations: number;
  tools: string[];
}

const route = useRoute();
const router = useRouter();
let teamId = route.params.id as string;

// ── 加载状态 ──
const loading = ref(false);
const saving = ref(false);

// ── 团队数据 ──
const team = ref<TeamConfig | null>(null);
const localName = ref('');
const localDescription = ref('');
const localTeamRules = ref('');
const localStartRole = ref('');
const localRoles = ref<RoleFormItem[]>([]);
const dirty = ref(false);

// ── 可用工具列表（从静态 NODE_TYPE_MAP 读取，不依赖 API）──
const availableNodeTypes = computed(() => {
  return Object.entries(NODE_TYPE_MAP)
    .filter(([type]) => type && !['_start', '_end'].includes(type))
    .map(([type, meta]) => ({ type, name: meta.label }));
});

// ── role 编辑器抽屉 ──
const showRoleDrawer = ref(false);
const editingDraft = ref<RoleFormItem | null>(null);
const editingIndex = ref(-1);

// ── SSE 运行 ──
const activeTab = ref('config');
const runInput = ref('');
const runLogs = ref<{ time: string; text: string; type: string }[]>([]);
const runResult = ref('');
const runError = ref('');
const running = ref(false);
let runController: AbortController | null = null;

const EVENT_ICONS: Record<string, string> = {
  team_start: '🚀',
  team_role_start: '🤖',
  team_handoff: '🔄',
  team_role_complete: '✅',
  workflow_complete: '🎉',
  workflow_error: '❌',
};

let saveTimer: ReturnType<typeof setTimeout> | null = null;

// ── 加载团队 ──
async function loadTeam() {
  if (teamId === 'new') {
    await showCreateDialog();
    return;
  }
  loading.value = true;
  try {
    const data = await getTeamDetailApi(teamId);
    team.value = data;
    localName.value = data.name;
    localDescription.value = data.description || '';
    localTeamRules.value = data.team_rules;
    localStartRole.value = data.start_role;
    localRoles.value = Object.entries(data.roles || {}).map(([key, role]) => ({
      key,
      agentDescription: (role as TeamRoleDef).agent_description || '',
      modelName: (role as TeamRoleDef).model_name || 'deepseek-chat',
      maxIterations: (role as TeamRoleDef).max_iterations ?? 25,
      tools: (role as TeamRoleDef).tools || [],
    }));
    dirty.value = false;
  } catch {
    ElMessage.error('加载团队失败');
    router.push('/ai-platform/team');
  } finally {
    loading.value = false;
  }
}

async function showCreateDialog() {
  try {
    const { value } = await ElMessageBox.prompt('请输入团队名称', '新建团队', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputValue: '新建团队',
      inputValidator: (v: string) => (v ? true : '名称不能为空'),
    });
    loading.value = true;
    try {
      const def = await createTeamApi({
        name: value || '新建团队',
        team_rules: '你们是一个出色的团队，致力于合作完成艰巨的工作。',
        start_role: '',
        roles: {},
      });
      teamId = def.id;
      router.replace(`/ai-platform/team/${def.id}`);
      await loadTeam();
    } finally {
      loading.value = false;
    }
  } catch {
    router.push('/ai-platform/team');
  }
}

// ── 自动保存（防抖） ──
function scheduleSave() {
  dirty.value = true;
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(doSave, 800);
}

async function doSave() {
  if (!team.value?.id) return;
  saving.value = true;
  try {
    const rolesDict: Record<string, TeamRoleDef> = {};
    for (const r of localRoles.value) {
      rolesDict[r.key] = {
        agent_description: r.agentDescription || undefined,
        model_name: r.modelName,
        max_iterations: r.maxIterations,
        tools: r.tools,
        termination_conditions: [],
      };
    }
    const updated = await updateTeamApi(team.value.id, {
      name: localName.value,
      description: localDescription.value || undefined,
      team_rules: localTeamRules.value,
      start_role: localStartRole.value,
      roles: rolesDict,
    });
    team.value = updated;
    dirty.value = false;
  } catch {
    ElMessage.error('保存失败');
  } finally {
    saving.value = false;
  }
}

// ── 手动保存 ──
async function handleSave() {
  if (!localName.value.trim()) {
    ElMessage.warning('请输入团队名称');
    return;
  }
  if (localRoles.value.length === 0) {
    ElMessage.warning('请至少添加一个角色');
    return;
  }
  if (saveTimer) clearTimeout(saveTimer);
  await doSave();
  ElMessage.success('已保存');
}

// ── 角色 CRUD ──
function addRole() {
  const idx = localRoles.value.length + 1;
  localRoles.value.push({
    key: `新角色${idx}`,
    agentDescription: '',
    modelName: 'deepseek-chat',
    maxIterations: 25,
    tools: [],
  });
  if (!localStartRole.value) {
    localStartRole.value = `新角色${idx}`;
  }
  scheduleSave();
}

function editRole(index: number) {
  editingIndex.value = index;
  const src = localRoles.value[index];
  if (!src) return;
  editingDraft.value = { ...src, tools: [...src.tools] };
  showRoleDrawer.value = true;
}

function closeRoleDrawer() {
  showRoleDrawer.value = false;
  editingDraft.value = null;
  editingIndex.value = -1;
}

function saveRoleDraft() {
  if (editingIndex.value < 0 || !editingDraft.value) return;
  localRoles.value[editingIndex.value] = { ...editingDraft.value };
  closeRoleDrawer();
  scheduleSave();
}

function deleteRole(index: number) {
  const removed = localRoles.value[index];
  if (!removed) return;
  localRoles.value.splice(index, 1);
  if (localStartRole.value === removed.key) {
    localStartRole.value = localRoles.value[0]?.key || '';
  }
  if (editingIndex.value === index) closeRoleDrawer();
  scheduleSave();
}

// onRoleKeyChange not needed; start_role updates via ElSelect v-model
function getTime(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
}

function handleRunEvent(event: { event: string; data: string }) {
  let text = event.event;
  try {
    const data = JSON.parse(event.data);
    switch (event.event) {
      case 'team_start':
        text = `团队 "${data.team_name}" 开始工作`;
        break;
      case 'team_role_start':
        text = `${data.role} 开始第${data.step}步`;
        runLogs.value = [];
        break;
      case 'team_handoff':
        text = `${data.from_role} → ${data.to_role}`;
        break;
      case 'team_role_complete':
        text = `${data.role} 完成`;
        break;
      case 'workflow_complete':
        text = '团队完成！';
        runResult.value = data.result || '';
        break;
      case 'workflow_error':
        text = '运行出错';
        runError.value = data.message || '未知错误';
        break;
      default:
        text = `${event.event}: ${JSON.stringify(data)}`;
    }
  } catch {
    text = event.data || event.event;
  }
  runLogs.value.push({ time: getTime(), text, type: event.event });
}

function startRun() {
  if (!team.value?.id) return;
  if (!runInput.value.trim()) {
    ElMessage.warning('请输入问题');
    return;
  }
  running.value = true;
  runLogs.value = [];
  runResult.value = '';
  runError.value = '';

  runController = new AbortController();

  requestClient
    .postSSE(
      `/api/ai-workflow/teams/${team.value.id}/stream`,
      { input_params: { input: runInput.value } },
      {
        signal: runController.signal,
        onMessage(content: string) {
          const lines = content.split('\n');
          for (const line of lines) {
            if (line.startsWith('data: [DONE]')) {
              running.value = false;
              return;
            }
            if (line.startsWith('data: ')) {
              try {
                const parsed = JSON.parse(line.slice(6));
                handleRunEvent(parsed);
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
          running.value = false;
        },
      },
    )
    .catch((err: Error) => {
      if (err.name !== 'AbortError') {
        runError.value = err.message || '连接失败';
        runLogs.value.push({ time: getTime(), text: `错误: ${err.message}`, type: 'error' });
      }
      running.value = false;
    });
}

function stopRun() {
  if (runController) {
    runController.abort();
    runController = null;
  }
  running.value = false;
}

// ── YAML ──
function copyYaml() {
  if (!team.value?.yaml_source) return;
  navigator.clipboard.writeText(team.value.yaml_source).then(() => {
    ElMessage.success('已复制');
  });
}

function downloadYaml() {
  if (!team.value?.yaml_source) return;
  const blob = new Blob([team.value.yaml_source], { type: 'text/yaml;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${team.value.name}.yaml`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── 导航 ──
const goBack = () => router.push('/ai-platform/team');

// ── 生命周期 ──
onMounted(async () => {
  await loadTeam();
});

onBeforeUnmount(() => {
  if (saveTimer) clearTimeout(saveTimer);
  if (runController) runController.abort();
});

// ── 监听变化触发自动保存 ──
watch([localName, localDescription, localTeamRules, localStartRole], () => {
  if (team.value?.id) scheduleSave();
});
watch(localRoles, () => {
  if (team.value?.id) scheduleSave();
}, { deep: true });
</script>

<template>
  <div class="team-editor" v-loading="loading">
    <!-- ═══ Header ═══ -->
    <header class="team-editor__header">
      <div class="header-left">
        <ElTooltip content="返回列表" placement="bottom">
          <ElButton text class="back-btn" @click="goBack">
            <ArrowLeft class="h-4 w-4" />
          </ElButton>
        </ElTooltip>
        <span class="header-title">{{ team?.name || '未命名团队' }}</span>
        <ElTag v-if="dirty" type="warning" size="small" effect="dark">未保存</ElTag>
      </div>
      <div class="header-right">
        <ElButton size="small" :loading="saving" @click="handleSave">
          <Save class="mr-1 h-3.5 w-3.5" />
          保存
        </ElButton>
        <ElButton type="primary" size="small" @click="activeTab = 'run'">
          <Play class="mr-1 h-3.5 w-3.5" />
          运行
        </ElButton>
      </div>
    </header>

    <!-- ═══ Body ═══ -->
    <div class="team-editor__body">
      <ElTabs v-model="activeTab" class="editor-tabs">
        <!-- ── 配置 Tab ── -->
        <ElTabPane label="配置" name="config">
          <div class="config-layout">
            <!-- 左侧主区域 -->
            <div class="config-main">
              <!-- 基本信息 -->
              <div class="section-card">
                <div class="section-title">基本信息</div>
                <div class="info-grid">
                  <div class="info-field">
                    <label>团队名称</label>
                    <ElInput v-model="localName" placeholder="团队名称" maxlength="200" />
                  </div>
                  <div class="info-field">
                    <label>描述</label>
                    <ElInput v-model="localDescription" type="textarea" :rows="2" placeholder="可选" />
                  </div>
                  <div class="info-field info-field--full">
                    <label>团队规则</label>
                    <ElInput v-model="localTeamRules" type="textarea" :rows="3" placeholder="定义团队协作规则和目标" />
                  </div>
                  <div class="info-field">
                    <label>起始角色</label>
                    <ElSelect v-model="localStartRole" placeholder="选择起始角色">
                      <ElOption
                        v-for="r in localRoles"
                        :key="r.key"
                        :label="r.key"
                        :value="r.key"
                      />
                    </ElSelect>
                  </div>
                </div>
              </div>

              <!-- 角色列表 -->
              <div class="section-card">
                <div class="section-title-row">
                  <span class="section-title">角色 ({{ localRoles.length }})</span>
                  <ElButton size="small" type="primary" plain @click="addRole">
                    <Plus class="mr-1 h-3.5 w-3.5" />
                    添加角色
                  </ElButton>
                </div>

                <div v-if="localRoles.length > 0" class="role-grid">
                  <div
                    v-for="(role, i) in localRoles"
                    :key="i"
                    class="role-card"
                    :class="{ 'role-card--active': showRoleDrawer && editingIndex === i }"
                    @click="editRole(i)"
                  >
                    <div class="role-card__emoji">🧑‍💼</div>
                    <div class="role-card__name">{{ role.key }}</div>
                    <div class="role-card__meta">模型: {{ role.modelName }}</div>
                    <div class="role-card__tools">
                      <ElTag
                        v-for="t in role.tools.slice(0, 3)"
                        :key="t"
                        size="small"
                        type="info"
                        effect="light"
                      >
                        {{ t }}
                      </ElTag>
                      <span v-if="role.tools.length > 3" class="tool-more">+{{ role.tools.length - 3 }}</span>
                    </div>
                  </div>
                </div>
                <ElEmpty v-else description="暂未添加角色，点击上方按钮" :image-size="80" />
              </div>
            </div>

            <!-- 右侧角色编辑抽屉 -->
            <Transition name="drawer-slide">
              <div v-if="showRoleDrawer && editingDraft" class="role-drawer">
                <div class="drawer-header">
                  <span class="drawer-title">编辑角色</span>
                  <ElButton text @click="closeRoleDrawer">
                    <X class="h-4 w-4" />
                  </ElButton>
                </div>
                <div class="drawer-body">
                  <div class="drawer-field">
                    <label>角色名称</label>
                    <ElInput
                      v-model="editingDraft.key"
                      size="small"
                      placeholder="角色名称"
                    />
                  </div>
                  <div class="drawer-field">
                    <label>模型</label>
                    <ElInput
                      v-model="editingDraft.modelName"
                      size="small"
                      placeholder="deepseek-chat"
                    />
                  </div>
                  <div class="drawer-field">
                    <label>最大迭代轮数</label>
                    <ElInputNumber
                      v-model="editingDraft.maxIterations"
                      size="small"
                      :min="1"
                      :max="100"
                      :style="{ width: '100%' }"
                    />
                  </div>
                  <div class="drawer-field">
                    <label>角色描述</label>
                    <ElInput
                      v-model="editingDraft.agentDescription"
                      type="textarea"
                      :rows="3"
                      size="small"
                      placeholder="描述该角色的职责和行为方式"
                    />
                  </div>
                  <div class="drawer-field">
                    <label>可用工具</label>
                    <div class="tool-checkboxes">
                      <ElCheckboxGroup v-model="editingDraft.tools">
                        <div
                          v-for="nt in availableNodeTypes"
                          :key="nt.type"
                          class="tool-check-item"
                        >
                          <ElCheckbox :label="nt.type" :value="nt.type">
                            {{ nt.name }}
                          </ElCheckbox>
                        </div>
                      </ElCheckboxGroup>
                      <div v-if="availableNodeTypes.length === 0" class="tool-empty">
                        暂无可用工具
                      </div>
                    </div>
                  </div>
                </div>
                <div class="drawer-footer">
                  <ElButton size="small" @click="deleteRole(editingIndex)">
                    <Trash2 class="mr-1 h-3.5 w-3.5" />
                    删除角色
                  </ElButton>
                  <div class="drawer-footer-right">
                    <ElButton size="small" @click="closeRoleDrawer">取消</ElButton>
                    <ElButton size="small" type="primary" @click="saveRoleDraft">保存</ElButton>
                  </div>
                </div>
              </div>
            </Transition>
          </div>
        </ElTabPane>

        <!-- ── 运行 Tab ── -->
        <ElTabPane label="运行" name="run">
          <div class="run-panel">
            <div class="run-input-section">
              <label class="run-label">输入问题</label>
              <ElInput
                v-model="runInput"
                class="run-input"
                type="textarea"
                :rows="2"
                placeholder="输入问题或任务描述..."
                :disabled="running"
              />
            </div>

            <div class="run-controls">
              <ElButton
                v-if="!running"
                type="primary"
                :disabled="!runInput.trim()"
                @click="startRun"
              >
                ▶ 开始运行
              </ElButton>
              <ElButton v-else type="danger" @click="stopRun">
                ⏹ 停止
              </ElButton>
            </div>

            <div v-if="runLogs.length > 0" class="run-logs">
              <div class="run-logs__header">执行日志</div>
              <div class="run-logs__body">
                <div
                  v-for="(log, i) in runLogs"
                  :key="i"
                  class="log-line"
                  :class="{
                    'log-line--error': log.type === 'workflow_error' || log.type === 'error',
                    'log-line--success': log.type === 'workflow_complete',
                  }"
                >
                  <span class="log-time">{{ log.time }}</span>
                  <span class="log-icon">{{ EVENT_ICONS[log.type] || '•' }}</span>
                  <span class="log-text">{{ log.text }}</span>
                </div>
              </div>
            </div>

            <div v-if="runResult" class="run-result">
              <div class="run-result__header">最终结果</div>
              <div class="run-result__body">{{ runResult }}</div>
            </div>

            <div v-if="runError" class="run-error">
              <div class="run-result__header" style="color: var(--el-color-danger)">错误</div>
              <div class="run-error__body">{{ runError }}</div>
            </div>
          </div>
        </ElTabPane>

        <!-- ── YAML Tab ── -->
        <ElTabPane label="YAML" name="yaml">
          <div class="yaml-panel">
            <div class="yaml-toolbar">
              <span class="yaml-label">YAML 源{{ team?.yaml_source ? '' : '（无）' }}</span>
              <div class="yaml-actions">
                <ElButton
                  v-if="team?.yaml_source"
                  size="small"
                  @click="copyYaml"
                >
                  <Copy class="mr-1 h-3.5 w-3.5" />
                  复制
                </ElButton>
                <ElButton
                  v-if="team?.yaml_source"
                  size="small"
                  @click="downloadYaml"
                >
                  <Download class="mr-1 h-3.5 w-3.5" />
                  下载
                </ElButton>
              </div>
            </div>
            <pre class="yaml-content">{{ team?.yaml_source || '# 暂无 YAML 源\n# 可通过导入 YAML 创建团队或编辑后自动生成' }}</pre>
          </div>
        </ElTabPane>
      </ElTabs>
    </div>
  </div>
</template>

<style scoped>
/* ── 全局容器 ── */
.team-editor {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #f8fafc;
}

/* ── Header ── */
.team-editor__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 52px;
  padding: 0 16px;
  background: #fff;
  border-bottom: 1px solid #e2e8f0;
  flex-shrink: 0;
  z-index: 20;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.back-btn {
  color: var(--el-text-color-secondary);
}

.header-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* ── Body ── */
.team-editor__body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 24px;
}

.editor-tabs {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.editor-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: auto;
}

.editor-tabs :deep(.el-tab-pane) {
  height: 100%;
}

/* ── 配置 Tab ── */
.config-layout {
  display: flex;
  gap: 20px;
  height: 100%;
  position: relative;
}

.config-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 基本信息卡片 */
.section-card {
  background: #fff;
  border-radius: 12px;
  padding: 16px 20px;
  border: 1px solid #e2e8f0;
}

.section-title {
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 12px;
  display: block;
}

.section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.info-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-field--full {
  grid-column: 1 / -1;
}

.info-field label {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
}

/* 角色卡片网格 */
.role-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}

.role-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 14px;
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.role-card:hover {
  border-color: #3b82f6;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);
}

.role-card--active {
  border-color: #3b82f6;
  background: #eff6ff;
}

.role-card__emoji {
  font-size: 24px;
  line-height: 1;
}

.role-card__name {
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
}

.role-card__meta {
  font-size: 11px;
  color: #64748b;
}

.role-card__tools {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  margin-top: 2px;
}

.tool-more {
  font-size: 10px;
  color: #94a3b8;
  line-height: 22px;
}

/* ── 右侧角色抽屉 ── */
.role-drawer {
  width: 340px;
  flex-shrink: 0;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  max-height: 100%;
  position: sticky;
  top: 0;
}

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid #e2e8f0;
}

.drawer-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.drawer-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.drawer-field label {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
}

.drawer-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-top: 1px solid #e2e8f0;
}

.drawer-footer-right {
  display: flex;
  gap: 8px;
}

.tool-checkboxes {
  max-height: 260px;
  overflow-y: auto;
}

.tool-check-item {
  padding: 3px 0;
}

.tool-empty {
  font-size: 12px;
  color: #94a3b8;
  padding: 8px 0;
}

/* 抽屉过渡动画 */
.drawer-slide-enter-active,
.drawer-slide-leave-active {
  transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.drawer-slide-enter-from,
.drawer-slide-leave-to {
  opacity: 0;
  transform: translateX(40px);
}

/* ── 运行 Tab ── */
.run-panel {
  max-width: 700px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.run-input-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.run-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.run-controls {
  display: flex;
  gap: 8px;
}

.run-logs {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
}

.run-logs__header {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  padding: 8px 12px;
  background: #f1f5f9;
  border-bottom: 1px solid #e2e8f0;
}

.run-logs__body {
  max-height: 300px;
  overflow-y: auto;
  padding: 8px 12px;
  background: #fff;
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
  color: #94a3b8;
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

.run-result {
  border: 1px solid var(--el-color-success-light-5);
  border-radius: 8px;
  overflow: hidden;
}

.run-result__header {
  font-size: 12px;
  font-weight: 600;
  padding: 8px 12px;
  background: var(--el-color-success-light-9);
  border-bottom: 1px solid var(--el-color-success-light-5);
}

.run-result__body {
  padding: 12px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  background: #fff;
  max-height: 200px;
  overflow-y: auto;
}

.run-error {
  border: 1px solid var(--el-color-danger-light-5);
  border-radius: 8px;
  overflow: hidden;
}

.run-error__body {
  padding: 12px;
  font-size: 13px;
  color: var(--el-color-danger);
  background: #fff;
  white-space: pre-wrap;
}

/* ── YAML Tab ── */
.yaml-panel {
  max-width: 800px;
}

.yaml-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.yaml-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.yaml-actions {
  display: flex;
  gap: 8px;
}

.yaml-content {
  background: #1e293b;
  color: #e2e8f0;
  padding: 16px 20px;
  border-radius: 10px;
  font-size: 12px;
  line-height: 1.6;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 60vh;
  overflow-y: auto;
  font-family: 'SF Mono', 'Consolas', monospace;
}
</style>
