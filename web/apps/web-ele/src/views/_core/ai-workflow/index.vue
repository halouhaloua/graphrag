<script setup lang="ts">
import type { WorkflowDef } from '#/api/core/ai-workflow';

import { onMounted, ref } from 'vue';

import { Page } from '@vben/common-ui';
import {
  Edit,
  Play,
  Plus,
  Send,
  Trash2,
  Workflow,
} from '@vben/icons';

import {
  ElButton,
  ElEmpty,
  ElInput,
  ElMessage,
  ElMessageBox,
  ElPagination,
  ElTooltip,
} from 'element-plus';
import { useRouter } from 'vue-router';

import {
  deleteWorkflowDefApi,
  getWorkflowDefListApi,
  publishWorkflowDefApi,
  runWorkflowApi,
} from '#/api/core/ai-workflow';

import WorkflowFormDialog from './modules/workflow-form-dialog.vue';

defineOptions({ name: 'AiWorkflowList' });

const router = useRouter();

// 搜索
const searchKeyword = ref('');

// 列表
const list = ref<WorkflowDef[]>([]);

// 分页
const pagination = ref({
  current: 1,
  pageSize: 12,
  total: 0,
});

// 状态
const loading = ref(false);
const showForm = ref(false);
const editingItem = ref<WorkflowDef | null>(null);

// 加载列表
const loadList = async () => {
  loading.value = true;
  try {
    const res = await getWorkflowDefListApi({
      page: pagination.value.current,
      pageSize: pagination.value.pageSize,
      name: searchKeyword.value || undefined,
    });
    list.value = res.items || [];
    pagination.value.total = res.total || 0;
  } catch {
    ElMessage.error('加载工作流列表失败');
  } finally {
    loading.value = false;
  }
};

// 新建
const handleCreate = () => {
  editingItem.value = null;
  showForm.value = true;
};

// 编辑
const handleEdit = (wf: WorkflowDef) => {
  editingItem.value = wf;
  showForm.value = true;
};

// 保存成功
const handleSaveSuccess = (newId?: string) => {
  showForm.value = false;
  loadList();
  if (newId) {
    router.push(`/ai-platform/workflow/${newId}`);
  }
};

// 查看详情（预留）
const handleView = (wf: WorkflowDef) => {
  router.push(`/ai-platform/workflow/${wf.id}`);
};

// 执行
const handleRun = async (wf: WorkflowDef) => {
  if (wf.workflow_type === 'app_workflow') {
    if (wf.workflow_route) {
      router.push(`/wf/app/${wf.workflow_route}`);
      return;
    }
    ElMessage.warning('应用工作流未配置路由');
    return;
  }
  try {
    await runWorkflowApi(wf.id);
    ElMessage.success(`工作流 "${wf.name}" 已启动执行`);
  } catch {
    ElMessage.error('启动失败');
  }
};

// 发布
const handlePublish = async (wf: WorkflowDef) => {
  try {
    await publishWorkflowDefApi(wf.id, !wf.is_published);
    ElMessage.success(wf.is_published ? '已取消发布' : '已发布');
    loadList();
  } catch {
    ElMessage.error('操作失败');
  }
};

// 删除
const handleDelete = async (wf: WorkflowDef) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除工作流 "${wf.name}" 吗？`,
      '删除确认',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' },
    );
    await deleteWorkflowDefApi(wf.id);
    ElMessage.success('已删除');
    loadList();
  } catch {
    // 取消操作
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

function copyRoute(wf: WorkflowDef) {
  const url = `/wf/${wf.workflow_type === 'ai_workflow' ? 'ai' : 'app'}/${wf.workflow_route}`;
  navigator.clipboard.writeText(window.location.origin + url);
  ElMessage.success('链接已复制');
}

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

onMounted(() => {
  loadList();
});
</script>

<template>
  <div class="ai-workflow-list">
    <Page auto-content-height v-loading="loading">
      <template #title>
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-4">
            <ElButton type="primary" @click="handleCreate">
              <Plus class="mr-1 h-4 w-4" />
              创建工作流
            </ElButton>
          </div>
          <div class="flex items-center gap-2">
            <ElInput
              v-model="searchKeyword"
              placeholder="搜索工作流名称"
              class="!w-64"
              clearable
              @clear="handleSearch"
              @keyup.enter="handleSearch"
            />
            <ElButton type="primary" @click="handleSearch">搜索</ElButton>
          </div>
        </div>
      </template>

      <!-- 卡片网格 -->
      <div
        v-if="list.length > 0"
        class="doc-grid"
      >
        <div
          v-for="wf in list"
          :key="wf.id"
          class="doc-card group"
          @click="handleView(wf)"
        >
          <!-- 头部 -->
          <div class="card-header">
            <div class="card-icon" :class="wf.is_published ? 'is-published' : 'is-draft'">
              <Workflow class="h-5 w-5" />
            </div>
            <div class="card-title-section">
              <h4 class="doc-name">{{ wf.name }}</h4>
            </div>
            <div class="card-actions">
              <ElTooltip content="编辑" placement="top">
                <ElButton circle size="small" class="action-btn" @click.stop="handleEdit(wf)">
                  <Edit style="width: 14px; height: 14px" />
                </ElButton>
              </ElTooltip>
              <ElTooltip content="执行" placement="top">
                <ElButton circle size="small" class="action-btn" :disabled="!wf.is_published" @click.stop="handleRun(wf)">
                  <Play style="width: 14px; height: 14px" />
                </ElButton>
              </ElTooltip>
              <ElTooltip :content="wf.is_published ? '取消发布' : '发布'" placement="top">
                <ElButton circle size="small" class="action-btn" @click.stop="handlePublish(wf)">
                  <Send style="width: 14px; height: 14px" />
                </ElButton>
              </ElTooltip>
              <ElTooltip content="删除" placement="top">
                <ElButton circle size="small" class="action-btn delete-btn" @click.stop="handleDelete(wf)">
                  <Trash2 style="width: 14px; height: 14px" />
                </ElButton>
              </ElTooltip>
            </div>
          </div>

          <!-- 描述 -->
          <div class="card-description">
            <p v-if="wf.description" class="desc-text">{{ wf.description }}</p>
            <p v-else class="desc-text empty">暂无描述</p>
          </div>

          <!-- 标签 -->
          <div class="card-status-row">
            <ElTag
              :type="wf.workflow_type === 'ai_workflow' ? 'primary' : 'warning'"
              size="small"
              effect="light"
            >
              {{ wf.workflow_type === 'ai_workflow' ? 'AI' : '应用' }}
            </ElTag>
            <ElTag :type="wf.is_published ? 'success' : 'info'" size="small" effect="light">
              {{ wf.is_published ? '已发布' : '未发布' }}
            </ElTag>
            <ElTag
              v-if="wf.is_published && wf.workflow_route"
              size="small"
              type="info"
              effect="plain"
              class="route-tag"
              @click.stop="copyRoute(wf)"
            >
              /{{ wf.workflow_type === 'ai_workflow' ? 'ai' : 'app' }}/{{ wf.workflow_route }}
            </ElTag>
          </div>

          <!-- 底部 -->
          <div class="card-footer">
              <span class="doc-subtitle">{{ wf.nodes?.length || 0 }} 个节点</span>
            <span class="footer-item time">{{ formatTime(wf.sys_create_datetime) }}</span>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <ElEmpty v-else description="暂无工作流，点击上方按钮创建" />

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

    <!-- 创建/编辑弹窗 -->
    <WorkflowFormDialog
      v-model="showForm"
      :workflow="editingItem"
      @success="handleSaveSuccess"
    />
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
  /* border: 1px solid var(--el-border-color-lighter); */
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

.card-icon.is-published {
  color: var(--el-color-success);
  background: var(--el-color-success-light-9);
}

.card-icon.is-draft {
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

.card-status-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.route-tag {
  cursor: pointer;
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 10px;
}

.route-tag:hover {
  color: var(--el-color-primary);
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
</style>
