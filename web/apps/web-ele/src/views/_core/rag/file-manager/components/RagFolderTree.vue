<script setup lang="ts">
import { Folder, FolderOpen } from '@vben/icons';
import { $t } from '@vben/locales';
import { ElTree } from 'element-plus';

import { getFileList } from '../api/rag-file';

import { useRagFileManager } from '../composables/useRagFileManager';

const props = defineProps<{
  fm: ReturnType<typeof useRagFileManager>;
}>();

const { navigateToFolder } = props.fm;

interface TreeData {
  id: null | string;
  name: string;
  isLeaf?: boolean;
}

const treeProps = {
  label: 'name',
  children: 'children',
  isLeaf: 'isLeaf',
};

const loadNode = async (node: any, resolve: (data: TreeData[]) => void) => {
  if (node.level === 0) {
    try {
      const res = await getFileList({
        parentId: null,
        fileType: 'folder',
        scope: props.fm.scope,
        page: 1,
        pageSize: 100,
      });
      const folders = res.items.map((item) => ({
        id: item.id!,
        name: item.name,
        isLeaf: false,
      }));
      return resolve(folders);
    } catch (error) {
      console.error('Failed to load root folders', error);
      return resolve([]);
    }
  }

  try {
    const parentId = node.data.id;
    const res = await getFileList({
      parentId,
      fileType: 'folder',
      scope: props.fm.scope,
      page: 1,
      pageSize: 100,
    });

    const folders = res.items.map((item) => ({
      id: item.id!,
      name: item.name,
      isLeaf: false,
    }));
    resolve(folders);
  } catch (error) {
    console.error('Failed to load folders', error);
    resolve([]);
  }
};

const handleNodeClick = (data: TreeData) => {
  navigateToFolder(data.id, data.name);
};
</script>

<template>
  <div class="flex-1 overflow-y-auto p-2">
    <ElTree
      lazy
      :load="loadNode"
      :props="treeProps"
      :expand-on-click-node="false"
      node-key="id"
      highlight-current
      @node-click="handleNodeClick"
    >
      <template #default="{ node }">
        <span class="flex items-center gap-2 py-1">
          <FolderOpen v-if="node.expanded" class="size-4 text-blue-500" />
          <Folder v-else class="size-4 text-gray-500" />
          <span class="truncate text-sm">{{ node.label }}</span>
        </span>
      </template>
    </ElTree>
  </div>
</template>

<style scoped lang="less">
:deep(.el-tree-node__content) {
  height: 34px;
  line-height: 34px;
  border-radius: 6px;
  margin-bottom: 4px;
}

:deep(.el-tree-node__expand-icon) {
  padding: 6px;
}

:deep(.el-tree-node.is-current > .el-tree-node__content) {
  background-color: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

:deep(.el-tree-node__content:hover) {
  background-color: var(--el-fill-color-light);
}

:deep(.el-tree-node.is-current > .el-tree-node__content:hover) {
  background-color: var(--el-color-primary-light-8);
}
</style>
