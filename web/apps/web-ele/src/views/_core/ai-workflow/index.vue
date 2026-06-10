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
} from '@vben/icons';

import {
  ElButton,
  ElCard,
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
        class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5"
      >
        <ElCard
          v-for="wf in list"
          :key="wf.id"
          shadow="hover"
          class="group workflow-card cursor-pointer transition-shadow"
          :body-style="{ padding: '0' }"
          style="border: none"
          @click="handleView(wf)"
        >
          <div class="p-4">
            <!-- 头部：图标 + 名称 + 操作 -->
            <div class="mb-3 flex items-center gap-3">
              <div class="wf-icon flex-shrink-0">
                <Send class="h-5 w-5 text-white" />
              </div>
              <div class="min-w-0 flex-1">
                <div class="flex items-center justify-between">
                  <div
                    class="min-w-0 flex-1 truncate text-sm font-medium"
                  >
                    {{ wf.name }}
                  </div>
                  <div
                    class="flex flex-shrink-0 items-center -space-x-1 opacity-0 transition-opacity group-hover:opacity-100"
                    @click.stop
                  >
                    <ElTooltip content="编辑" placement="top">
                      <ElButton text size="small" @click="handleEdit(wf)">
                        <Edit class="h-3.5 w-3.5" />
                      </ElButton>
                    </ElTooltip>
                    <ElTooltip content="执行" placement="top">
                      <ElButton text size="small" @click="handleRun(wf)">
                        <Play class="h-3.5 w-3.5" />
                      </ElButton>
                    </ElTooltip>
                    <ElTooltip
                      :content="wf.is_published ? '取消发布' : '发布'"
                      placement="top"
                    >
                      <ElButton text size="small" @click="handlePublish(wf)">
                        <Send class="h-3.5 w-3.5" />
                      </ElButton>
                    </ElTooltip>
                    <ElTooltip content="删除" placement="top">
                      <ElButton text size="small" @click="handleDelete(wf)">
                        <Trash2 class="h-3.5 w-3.5" />
                      </ElButton>
                    </ElTooltip>
                  </div>
                </div>
              </div>
            </div>

            <!-- 描述 -->
            <div
              v-if="wf.description"
              class="text-muted-foreground mb-3 line-clamp-2 text-xs"
            >
              {{ wf.description }}
            </div>

            <!-- 底部：节点数 + 状态 + 创建时间 -->
            <div class="flex items-center justify-between">
              <div class="flex gap-1">
                <ElTag size="small">
                  {{ wf.nodes?.length || 0 }} 个节点
                </ElTag>
                <ElTag
                  size="small"
                  :type="wf.is_published ? 'success' : 'info'"
                >
                  {{ wf.is_published ? '已发布' : '未发布' }}
                </ElTag>
              </div>
              <span class="text-muted-foreground text-xs">
                {{ wf.sys_create_datetime }}
              </span>
            </div>
          </div>
        </ElCard>
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
.workflow-card :deep(.el-card__body) {
  padding: 0;
}

.wf-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: linear-gradient(
    135deg,
    var(--el-color-primary-light-3),
    var(--el-color-primary)
  );
  border-radius: 8px;
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
