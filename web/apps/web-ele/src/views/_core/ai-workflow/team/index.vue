<script setup lang="ts">
import type { TeamConfig } from '#/api/core/ai-workflow';

import { onMounted, ref } from 'vue';

import { Page } from '@vben/common-ui';
import {
  Download,
  Edit,
  Play,
  Plus,
  Trash2,
  Upload,
  Users,
} from '@vben/icons';

import {
  ElButton,
  ElDialog,
  ElEmpty,
  ElInput,
  ElMessage,
  ElMessageBox,
  ElPagination,
  ElTag,
  ElTooltip,
} from 'element-plus';
import { useRouter } from 'vue-router';

import {
  createTeamApi,
  deleteTeamApi,
  getTeamListApi,
  importTeamYamlApi,
} from '#/api/core/ai-workflow';

import TeamRunDialog from './modules/team-run-dialog.vue';

defineOptions({ name: 'AiWorkflowTeamList' });

const router = useRouter();

// 搜索
const searchKeyword = ref('');

// 列表
const list = ref<TeamConfig[]>([]);

// 分页
const pagination = ref({
  current: 1,
  pageSize: 12,
  total: 0,
});

// 状态
const loading = ref(false);
const showRun = ref(false);
const showYamlImport = ref(false);
const runningItem = ref<TeamConfig | null>(null);
const yamlContent = ref('');
const yamlImporting = ref(false);

// 加载列表
const loadList = async () => {
  loading.value = true;
  try {
    const res = await getTeamListApi({
      page: pagination.value.current,
      pageSize: pagination.value.pageSize,
      name: searchKeyword.value || undefined,
    });
    list.value = res.items || [];
    pagination.value.total = res.total || 0;
  } catch {
    ElMessage.error('加载团队列表失败');
  } finally {
    loading.value = false;
  }
};

// 新建（同流程编排：弹窗创建后跳转到详情编辑器）
const handleCreate = async () => {
  try {
    const { value } = await ElMessageBox.prompt('请输入团队名称', '新建团队', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputValue: '新建团队',
      inputValidator: (v: string) => (v ? true : '名称不能为空'),
    });
    const team = await createTeamApi({
      name: value || '新建团队',
      team_rules: '你们是一个出色的团队，致力于合作完成艰巨的工作。',
      start_role: '',
      roles: {},
    });
    router.push(`/ai-platform/team/${team.id}`);
  } catch {
    // 取消操作
  }
};

// 编辑 → 导航到详情编辑器
const handleEdit = (team: TeamConfig) => {
  router.push(`/ai-platform/team/${team.id}`);
};

// 运行
const handleRun = (team: TeamConfig) => {
  runningItem.value = team;
  showRun.value = true;
};

// 删除
const handleDelete = async (team: TeamConfig) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除团队 "${team.name}" 吗？`,
      '删除确认',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' },
    );
    await deleteTeamApi(team.id);
    ElMessage.success('已删除');
    loadList();
  } catch {
    // 取消操作
  }
};

// 导出 YAML
const handleExportYaml = (team: TeamConfig) => {
  if (!team.yaml_source) {
    ElMessage.warning('该团队无 YAML 源');
    return;
  }
  const blob = new Blob([team.yaml_source], { type: 'text/yaml;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${team.name}.yaml`;
  a.click();
  URL.revokeObjectURL(url);
};

// 导入 YAML
const handleImportYaml = async () => {
  if (!yamlContent.value.trim()) {
    ElMessage.warning('请输入 YAML 内容');
    return;
  }
  yamlImporting.value = true;
  try {
    await importTeamYamlApi({ yaml_content: yamlContent.value });
    ElMessage.success('导入成功');
    showYamlImport.value = false;
    yamlContent.value = '';
    loadList();
  } catch {
    ElMessage.error('导入失败');
  } finally {
    yamlImporting.value = false;
  }
};

// 搜索
const handleSearch = () => {
  pagination.value.current = 1;
  loadList();
};

// 分页
const handlePageChange = (page: number) => {
  pagination.value.current = page;
  loadList();
};

const handleSizeChange = (size: number) => {
  pagination.value.pageSize = size;
  pagination.value.current = 1;
  loadList();
};

onMounted(() => {
  loadList();
});

function formatTime(dateStr?: string): string {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const h = String(d.getHours()).padStart(2, '0');
    const min = String(d.getMinutes()).padStart(2, '0');
    return `${y}-${m}-${day} ${h}:${min}`;
  } catch {
    return dateStr;
  }
}

function getRoleNames(roles: Record<string, any>): string[] {
  return Object.keys(roles || {});
}
</script>

<template>
  <div class="ai-workflow-list">
    <Page auto-content-height v-loading="loading">
      <template #title>
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-4">
            <ElButton type="primary" @click="handleCreate">
              <Plus class="mr-1 h-4 w-4" />
              创建团队
            </ElButton>
            <ElButton @click="showYamlImport = true">
              <Upload class="mr-1 h-4 w-4" />
              导入 YAML
            </ElButton>
          </div>
          <div class="flex items-center gap-2">
            <ElInput
              v-model="searchKeyword"
              placeholder="搜索团队名称"
              class="!w-64"
              clearable
              @clear="handleSearch"
              @keyup.enter="handleSearch"
            />
            <ElButton type="primary" @click="handleSearch">搜索</ElButton>
          </div>
        </div>
      </template>

      <!-- 卡片网格（与流程编排完全一致） -->
      <div v-if="list.length > 0" class="doc-grid">
        <div
          v-for="team in list"
          :key="team.id"
          class="doc-card group"
          @click="handleEdit(team)"
        >
          <!-- 头部 -->
          <div class="card-header">
            <div class="card-icon is-team">
              <Users class="h-5 w-5" />
            </div>
            <div class="card-title-section">
              <h4 class="doc-name">{{ team.name }}</h4>
            </div>
            <div class="card-actions">
              <ElTooltip content="编辑" placement="top">
                <ElButton circle size="small" class="action-btn" @click.stop="handleEdit(team)">
                  <Edit style="width: 14px; height: 14px" />
                </ElButton>
              </ElTooltip>
              <ElTooltip content="运行" placement="top">
                <ElButton circle size="small" class="action-btn" @click.stop="handleRun(team)">
                  <Play style="width: 14px; height: 14px" />
                </ElButton>
              </ElTooltip>
              <ElTooltip content="导出 YAML" placement="top">
                <ElButton circle size="small" class="action-btn" @click.stop="handleExportYaml(team)">
                  <Download style="width: 14px; height: 14px" />
                </ElButton>
              </ElTooltip>
              <ElTooltip content="删除" placement="top">
                <ElButton circle size="small" class="action-btn delete-btn" @click.stop="handleDelete(team)">
                  <Trash2 style="width: 14px; height: 14px" />
                </ElButton>
              </ElTooltip>
            </div>
          </div>

          <!-- 描述 -->
          <div class="card-description">
            <p v-if="team.description" class="desc-text">{{ team.description }}</p>
            <p v-else class="desc-text empty">暂无描述</p>
          </div>

          <!-- 角色标签 -->
          <div class="card-tags">
            <ElTag
              v-for="role in getRoleNames(team.roles)"
              :key="role"
              size="small"
              type="info"
              effect="light"
            >
              {{ role }}
            </ElTag>
          </div>

          <!-- 底部 -->
          <div class="card-footer">
            <span class="doc-subtitle">{{ getRoleNames(team.roles).length }} 个角色</span>
            <span class="footer-item time">{{ formatTime(team.sys_create_datetime) }}</span>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <ElEmpty v-else description="暂无团队，点击上方按钮创建" />

      <!-- 分页 -->
      <template #footer>
        <div class="flex w-full items-center justify-end">
          <ElPagination
            v-model:current-page="pagination.current"
            v-model:page-size="pagination.pageSize"
            :total="pagination.total"
            :page-sizes="[12, 24, 36, 48]"
            :pager-count="7"
            layout="total, sizes, prev, pager, next, jumper"
            background
            size="small"
            @current-change="handlePageChange"
            @size-change="handleSizeChange"
          />
        </div>
      </template>
    </Page>

    <!-- 运行弹窗 -->
    <TeamRunDialog
      v-model="showRun"
      :team="runningItem"
    />

    <!-- 导入 YAML -->
    <ElDialog
      v-model="showYamlImport"
      title="从 YAML 导入团队"
      width="640px"
      :close-on-click-modal="false"
    >
      <ElInput
        v-model="yamlContent"
        type="textarea"
        :rows="16"
        placeholder="粘贴 YAML 配置内容..."
      />
      <div class="yaml-hint">
        支持从 YAML 文件导入团队配置。粘贴完整的 YAML 内容后点击"导入"。
      </div>
      <template #footer>
        <ElButton @click="showYamlImport = false">取消</ElButton>
        <ElButton type="primary" :loading="yamlImporting" @click="handleImportYaml">
          导入
        </ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<style scoped>
.doc-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.doc-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 20px;
  cursor: pointer;
  background: var(--el-bg-color);
  border-radius: 12px;
  transition: all 0.25s ease;
}

.doc-card:hover {
  border-color: var(--el-border-color);
  box-shadow: 0 4px 16px rgb(0 0 0 / 6%);
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.card-icon {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 8px;
}

.card-icon.is-team {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.card-title-section {
  flex: 1;
  min-width: 0;
}

.doc-name {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
}

.doc-subtitle {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.card-actions {
  display: flex;
  flex-shrink: 0;
  gap: 2px;
  align-items: center;
  opacity: 0;
  transition: opacity 0.15s;
}

.doc-card:hover .card-actions {
  opacity: 1;
}

.action-btn {
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--el-text-color-secondary);
  background: transparent;
  border: none;
}

.action-btn:hover {
  color: var(--el-text-color-primary);
  background: var(--el-fill-color-lighter);
}

.action-btn.delete-btn:hover:not(:disabled) {
  color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
}

.card-description {
  min-height: 20px;
}

.desc-text {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  -webkit-line-clamp: 2;
  font-size: 13px;
  line-height: 1.5;
  color: var(--el-text-color-regular);
  -webkit-box-orient: vertical;
}

.desc-text.empty {
  font-style: italic;
  color: var(--el-text-color-placeholder);
}

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-height: 24px;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.footer-item {
  display: flex;
  gap: 4px;
  align-items: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.footer-item.time {
  color: var(--el-text-color-placeholder);
}

.yaml-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
</style>
