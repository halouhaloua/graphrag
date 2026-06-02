import { ref, shallowRef } from 'vue';

import { getKbFileList, getKbFileTree } from '../api/rag-file';

export function useKbFileManager() {

  const currentKbId = ref<null | string>(null);
  const viewMode = ref<'grid' | 'list'>('grid');
  const selectedFileIds = ref<Set<string>>(new Set());
  const fileList = shallowRef<any[]>([]);
  const loading = ref(false);
  const searchQuery = ref('');
  const breadcrumbs = ref<Array<{ id: null | string; name: string }>>([
    { id: null, name: '知识库资料' },
  ]);
  const createFolderDialogVisible = ref(false);

  const toggleViewMode = () => {
    viewMode.value = viewMode.value === 'grid' ? 'list' : 'grid';
  };

  const fetchFiles = async (_creatorId?: string) => {
    if (!currentKbId.value) {
      loading.value = true;
      try {
        const res: any = await getKbFileTree();
        fileList.value = (res || []).map((kb: any) => ({
          id: kb.id,
          name: kb.name,
          fileType: 'folder',
          hasChildren: true,
        }));
      } catch (error) {
        console.error(error);
        fileList.value = [];
      } finally {
        loading.value = false;
      }
      return;
    }
    loading.value = true;
    try {
      const res = await getKbFileList(currentKbId.value);
      fileList.value = (res.items || []).map((item: any) => ({
        id: item.id,
        name: item.filename,
        fileType: 'file',
        fileSize: item.file_size,
        fileExt: item.file_type,
        kbId: item.kb_id,
        kbName: item.kb_name,
      }));
    } catch (error) {
      console.error(error);
    } finally {
      loading.value = false;
    }
  };

  const navigateToFolder = (folderId: null | string, folderName?: string) => {
    currentKbId.value = folderId;
    selectedFileIds.value.clear();

    if (folderId === null) {
      breadcrumbs.value = [{ id: null, name: '知识库资料' }];
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
    // no-op: KB files don't have folders
  };

  return {
    currentFolderId: currentKbId,
    viewMode,
    selectedFileIds,
    fileList,
    loading,
    searchQuery,
    breadcrumbs,
    createFolderDialogVisible,
    scope: 'kb' as const,
    toggleViewMode,
    navigateToFolder,
    toggleSelection,
    clearSelection,
    fetchFiles,
    openCreateFolderDialog,
  };
}
