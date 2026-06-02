<script lang="ts" setup>
import type { KnowledgeBase } from '#/api/core/rag';

import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { Plus } from '@vben/icons';

import { ElButton, ElInput, ElMessage, ElPagination } from 'element-plus';

import {
  createKnowledgeBaseApi,
  getKnowledgeBaseListApi,
  updateKnowledgeBaseApi,
} from '#/api/core/rag';

import DescriptionEditor from './modules/description-editor.vue';
import DocCard from './modules/doc-card.vue';
import KbFormDialog from './modules/kb-form-dialog.vue';

defineOptions({ name: 'DocumentView' });

const router = useRouter();
const kbs = ref<KnowledgeBase[]>([]);
const searchQuery = ref('');
const loading = ref(false);
const descEditorRef = ref<InstanceType<typeof DescriptionEditor>>();
const formDialogRef = ref<InstanceType<typeof KbFormDialog>>();

const currentPage = ref(1);
const pageSize = ref(12);
const pageSizes = [12, 24, 36, 48];

const filteredKbs = computed(() => {
  if (!searchQuery.value.trim()) return kbs.value;
  const q = searchQuery.value.toLowerCase();
  return kbs.value.filter(
    (kb) =>
      kb.name.toLowerCase().includes(q) ||
      (kb.description || '').toLowerCase().includes(q),
  );
});

const paginatedKbs = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return filteredKbs.value.slice(start, start + pageSize.value);
});

const totalItems = computed(() => filteredKbs.value.length);

function handlePageChange(page: number) {
  currentPage.value = page;
}

function handleSizeChange(size: number) {
  pageSize.value = size;
  currentPage.value = 1;
}

function handleSearchInput(val: string) {
  searchQuery.value = val;
  currentPage.value = 1;
}

async function loadKbs() {
  loading.value = true;
  try {
    const res = await getKnowledgeBaseListApi({ page: 1, pageSize: 200 });
    kbs.value = res.items;
  } catch {
    ElMessage.error('加载知识库列表失败');
  } finally {
    loading.value = false;
  }
}

function handleCardClick(kb: KnowledgeBase) {
  router.push(`/rag/knowledge-base/${kb.id}`);
}

function handleCardAction(kb: KnowledgeBase) {
  router.push(`/rag/knowledge-base/${kb.id}`);
}

function openEdit(kb: KnowledgeBase) {
  descEditorRef.value?.open(kb);
}

function handleCreate() {
  formDialogRef.value?.open();
}

async function handleSave(
  data: { description?: string; name: string },
  editId?: string,
) {
  if (editId) {
    await updateKnowledgeBaseApi(editId, data);
    ElMessage.success('更新成功');
  } else {
    await createKnowledgeBaseApi(data);
    ElMessage.success('创建成功');
  }
  loadKbs();
}

onMounted(() => {
  loadKbs();
});
</script>

<template>
  <Page auto-content-height v-loading="loading">
    <template #title>
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <span class="text-base font-semibold">知识库管理</span>
          <span
            class="rounded-full bg-muted px-3 py-0.5 text-xs text-muted-foreground"
          >
            {{ filteredKbs.length }} 个知识库
          </span>
          <ElButton type="primary" :icon="Plus" @click="handleCreate">
            新建知识库
          </ElButton>
        </div>
        <div class="flex items-center gap-2">
          <ElInput
            v-model="searchQuery"
            placeholder="搜索知识库..."
            clearable
            class="!w-64"
            @input="handleSearchInput"
          />
        </div>
      </div>
    </template>

    <div class="doc-grid">
      <div v-if="paginatedKbs.length === 0 && !loading" class="empty-state">
        <div class="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <svg
            width="64"
            height="64"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1"
            class="mb-4"
          >
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
          <p>{{ searchQuery ? '未找到匹配的知识库' : '暂无知识库' }}</p>
          <ElButton v-if="!searchQuery" type="primary" class="mt-3" @click="handleCreate">
            创建第一个知识库
          </ElButton>
        </div>
      </div>
      <DocCard
        v-for="kb in paginatedKbs"
        :key="kb.id"
        :kb="kb"
        :description="kb.description || ''"
        @click="handleCardClick(kb)"
        @edit="openEdit(kb)"
        @deleted="loadKbs"
        @view-graph="handleCardAction(kb)"
        @construct="handleCardAction(kb)"
        @upload-schema="handleCardAction(kb)"
      />
    </div>

    <template #footer>
      <div class="flex w-full items-center justify-end">
        <ElPagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="totalItems"
          :page-sizes="pageSizes"
          layout="total, sizes, prev, pager, next, jumper"
          background
          size="small"
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </template>

    <DescriptionEditor ref="descEditorRef" @saved="loadKbs" />
    <KbFormDialog ref="formDialogRef" @save="handleSave" />
  </Page>
</template>

<style scoped>
.doc-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.empty-state {
  grid-column: 1 / -1;
}
</style>
