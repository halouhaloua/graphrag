<script setup lang="ts">
import { useRouter } from 'vue-router';
import { Folder, FolderOpen, FileText } from '@vben/icons';
import { ElTree } from 'element-plus';

import { getKbFileTree, getKbFileList } from '../api/rag-file';
import { useKbFileManager } from '../composables/useKbFileManager';

const router = useRouter();

const props = defineProps<{
  fm: ReturnType<typeof useKbFileManager>;
}>();

const { navigateToFolder } = props.fm;

interface TreeData {
  id: string;
  name: string;
  isLeaf?: boolean;
  fileType?: string;
}

const treeProps = {
  label: 'name',
  children: 'children',
  isLeaf: 'isLeaf',
};

const loadNode = async (node: any, resolve: (data: TreeData[]) => void) => {
  if (node.level === 0) {
    try {
      const res: any = await getKbFileTree();
      return resolve(
        (res || []).map((kb: any) => ({
          id: kb.id,
          name: kb.name,
          isLeaf: false,
          fileType: 'folder',
        })),
      );
    } catch (error) {
      console.error('Failed to load KB tree', error);
      return resolve([]);
    }
  }

  try {
    const kbId = node.data.id;
    const res: any = await getKbFileList(kbId);
    const files = (res.items || []).map((item: any) => ({
      id: item.id,
      name: item.filename,
      isLeaf: true,
      fileType: 'file',
      kbId,
    }));
    resolve(files);
  } catch (error) {
    console.error('Failed to load KB files', error);
    resolve([]);
  }
};

const handleNodeClick = (data: TreeData) => {
  if (data.fileType === 'folder') {
    navigateToFolder(data.id, data.name);
  } else {
    const { kbId } = data as any;
    router.push(`/rag/kb-file/${data.id}/task?kbId=${kbId}`);
  }
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
      <template #default="{ node, data }">
        <span class="flex items-center gap-2 py-1">
          <FolderOpen
            v-if="node.expanded && data.fileType === 'folder'"
            class="size-4 text-blue-500"
          />
          <Folder
            v-else-if="data.fileType === 'folder'"
            class="size-4 text-gray-500"
          />
          <FileText v-else class="size-4 text-gray-400" />
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
