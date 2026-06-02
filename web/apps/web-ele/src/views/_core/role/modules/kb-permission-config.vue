<script lang="ts" setup>
import type { KnowledgeBase } from '#/api/core/rag';

import { ref, watch, computed } from 'vue';

import {
  ElButton,
  ElCard,
  ElEmpty,
  ElInput,
  ElMessage,
  ElPagination,
  ElScrollbar,
  ElSkeleton,
  ElSkeletonItem,
  ElTag,
} from 'element-plus';

import {
  getKnowledgeBaseListApi,
  getRoleKbPermissionsApi,
  updateRoleKbPermissionsApi,
} from '#/api/core/rag';

const props = defineProps<{
  roleId: string;
  height: number;
}>();

const emit = defineEmits<{ success: [] }>();

const loading = ref(false);
const saving = ref(false);
const allKbs = ref<KnowledgeBase[]>([]);
const selectedMap = ref<Record<string, boolean>>({});
const searchQuery = ref('');
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);

const selectedCount = computed(
  () => Object.values(selectedMap.value).filter(Boolean).length,
);

async function loadData() {
  if (!props.roleId) return;
  loading.value = true;
  try {
    const [listRes, roleKbsRes] = await Promise.all([
      getKnowledgeBaseListApi({
        page: page.value,
        pageSize: pageSize.value,
        name: searchQuery.value || undefined,
      }),
      getRoleKbPermissionsApi(props.roleId),
    ]);
    allKbs.value = listRes.items ?? [];
    total.value = listRes.total;
    const map: Record<string, boolean> = {};
    for (const kb of roleKbsRes.items ?? []) {
      map[kb.id] = true;
    }
    selectedMap.value = map;
  } catch (error) {
    console.error('加载知识库数据失败', error);
    ElMessage.error('加载知识库数据失败');
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.roleId,
  (id) => {
    searchQuery.value = '';
    page.value = 1;
    if (id) {
      loadData();
    } else {
      allKbs.value = [];
      selectedMap.value = {};
    }
  },
);

watch([page, pageSize], () => {
  if (props.roleId) loadData();
});

let searchTimer: ReturnType<typeof setTimeout> | null = null;

watch(searchQuery, () => {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    page.value = 1;
    if (props.roleId) loadData();
  }, 300);
});

function toggleKb(kbId: string, checked: boolean) {
  selectedMap.value = { ...selectedMap.value, [kbId]: checked };
}

function selectAll() {
  const newMap: Record<string, boolean> = {};
  allKbs.value.forEach((kb) => { newMap[kb.id] = true; });
  selectedMap.value = { ...selectedMap.value, ...newMap };
}

function unselectAll() {
  const newMap = { ...selectedMap.value };
  allKbs.value.forEach((kb) => { delete newMap[kb.id]; });
  selectedMap.value = newMap;
}

async function save() {
  if (!props.roleId) return;
  saving.value = true;
  try {
    const kbIds = Object.entries(selectedMap.value)
      .filter(([, v]) => v)
      .map(([k]) => k);
    await updateRoleKbPermissionsApi(props.roleId, kbIds);
    ElMessage.success('知识库权限更新成功');
    emit('success');
  } catch (error) {
    console.error('保存知识库权限失败', error);
    ElMessage.error('保存知识库权限失败');
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <ElCard
    class="flex flex-col border border-[var(--el-border-color)]"
    shadow="never"
    :style="{ height: `${height}px` }"
    :body-style="{ padding: '0', display: 'flex', flexDirection: 'column', height: '100%' }"
  >
    <!-- 内容区 -->
    <div class="flex min-h-0 flex-1 flex-col">
      <!-- 加载骨架屏 -->
      <div v-if="loading" class="flex-1 p-3">
        <ElSkeleton :loading="true" animated :throttle="0">
          <template #template>
            <div class="space-y-2 p-2">
              <div v-for="i in 12" :key="i" class="flex h-[36px] items-center gap-3">
                <ElSkeletonItem variant="text" style="width: 14px; height: 14px; border-radius: 3px" />
                <ElSkeletonItem variant="text" :style="{ width: `${40 + Math.random() * 40}%`, height: '14px' }" />
              </div>
            </div>
          </template>
        </ElSkeleton>
      </div>

      <!-- 空状态 -->
      <div v-else-if="allKbs.length === 0" class="flex flex-1 items-center justify-center">
        <ElEmpty description="暂无知识库数据" />
      </div>

      <!-- 正常内容 -->
      <template v-else>
        <!-- 工具栏 -->
        <div class="flex items-center justify-between px-4 py-2">
          <div class="flex items-center gap-3">
            <ElInput v-model="searchQuery" placeholder="搜索知识库..." clearable style="width: 240px" size="small" />
            <span class="text-xs text-gray-400">已选 {{ selectedCount }}/{{ total }}</span>
          </div>
          <div class="flex gap-1">
            <ElButton link type="primary" size="small" @click="selectAll">全选当前页</ElButton>
            <ElButton link type="primary" size="small" @click="unselectAll">取消当前页</ElButton>
          </div>
        </div>

        <!-- 知识库列表 -->
        <ElScrollbar class="flex-1">
          <div class="p-2">
            <div
              v-for="kb in allKbs"
              :key="kb.id"
              class="flex h-[36px] cursor-pointer items-center rounded-[6px] px-2 transition-colors hover:bg-[var(--el-fill-color-light)]"
              @click="toggleKb(kb.id, !selectedMap[kb.id])"
            >
              <input
                type="checkbox"
                :checked="!!selectedMap[kb.id]"
                class="mr-2 size-3.5 flex-shrink-0 cursor-pointer rounded border-gray-300 transition-colors"
                @change="toggleKb(kb.id, ($event.target as HTMLInputElement).checked)"
                @click.stop
              />
              <span class="flex-1 truncate text-xs" :title="kb.name">{{ kb.name }}</span>
              <ElTag v-if="kb.kb_type === 'demo'" size="small" type="info" class="flex-shrink-0" style="height: 20px; line-height: 20px">演示</ElTag>
              <span class="ml-2 flex-shrink-0 text-xs text-gray-400">{{ kb.file_count }} 个文件</span>
              <span v-if="kb.description" class="ml-2 max-w-36 flex-shrink-0 truncate text-xs text-gray-400" :title="kb.description">{{ kb.description }}</span>
            </div>
          </div>
        </ElScrollbar>

        <!-- 分页 -->
        <div class="flex items-center justify-between px-2 py-2">
          <div class="flex gap-1">
            <ElButton :loading="saving" type="primary" size="small" @click="save">保存</ElButton>
          </div>
          <ElPagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="total"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next"
            small
          />
        </div>
      </template>
    </div>
  </ElCard>
</template>
