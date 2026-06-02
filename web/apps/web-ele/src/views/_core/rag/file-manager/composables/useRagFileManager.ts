import type { RagFileApi } from '../api/rag-file';

import { ref, shallowRef } from 'vue';

import { getFileList } from '../api/rag-file';

export function useRagFileManager(scope: 'personal' | 'shared') {
  const currentFolderId = ref<null | string>(null);
  const viewMode = ref<'grid' | 'list'>('list');
  const selectedFileIds = ref<Set<string>>(new Set());
  const fileList = shallowRef<RagFileApi.FileItem[]>([]);
  const loading = ref(false);
  const breadcrumbs = ref<Array<{ id: null | string; name: string }>>([
    { id: null, name: scope === 'personal' ? '个人资料' : '共建资料' },
  ]);
  const createFolderDialogVisible = ref(false);

  const toggleViewMode = () => {
    viewMode.value = viewMode.value === 'grid' ? 'list' : 'grid';
  };

  const fetchFiles = async (creatorId?: string) => {
    loading.value = true;
    try {
      const params: RagFileApi.FileListParams = {
        parentId: currentFolderId.value,
        scope,
        page: 1,
        pageSize: 100,
      };
      if (scope === 'personal' && creatorId) {
        params.creatorId = creatorId;
      }
      const res = await getFileList(params);
      fileList.value = res.items;
    } catch (error) {
      console.error(error);
    } finally {
      loading.value = false;
    }
  };

  const navigateToFolder = (folderId: null | string, folderName?: string) => {
    currentFolderId.value = folderId;
    selectedFileIds.value.clear();

    if (folderId === null) {
      breadcrumbs.value = [
        {
          id: null,
          name: scope === 'personal' ? '个人资料' : '共建资料',
        },
      ];
    } else if (folderName) {
      const index = breadcrumbs.value.findIndex((b) => b.id === folderId);
      if (index === -1) {
        breadcrumbs.value.push({ id: folderId, name: folderName });
      } else {
        breadcrumbs.value = breadcrumbs.value.slice(0, index + 1);
      }
    }
    fetchFiles();
  };

  const toggleSelection = (id: string, multi: boolean) => {
    if (multi) {
      if (selectedFileIds.value.has(id)) {
        selectedFileIds.value.delete(id);
      } else {
        selectedFileIds.value.add(id);
      }
    } else {
      selectedFileIds.value.clear();
      selectedFileIds.value.add(id);
    }
  };

  const clearSelection = () => {
    selectedFileIds.value.clear();
  };

  const openCreateFolderDialog = () => {
    createFolderDialogVisible.value = true;
  };

  return {
    currentFolderId,
    viewMode,
    selectedFileIds,
    fileList,
    loading,
    breadcrumbs,
    createFolderDialogVisible,
    scope,
    toggleViewMode,
    navigateToFolder,
    toggleSelection,
    clearSelection,
    fetchFiles,
    openCreateFolderDialog,
  };
}
