<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import {
  FileArchive,
  FileAudio,
  FileImage,
  FileText,
  FileVideo,
  Folder,
  MoreVertical,
} from '@vben/icons';

import { $t } from '@vben/locales';
import {
  ElCheckbox,
  ElDropdown,
  ElDropdownItem,
  ElDropdownMenu,
  ElEmpty,
  ElMessage,
  ElMessageBox,
  ElTable,
  ElTableColumn,
  ElImageViewer as ImageViewer,
} from 'element-plus';

import type { RagFileApi } from '../api/rag-file';
import { deleteItem, getDownloadUrl, getFileStreamUrl, getKbFileStreamUrl } from '../api/rag-file';
import { useAccessStore } from '@vben/stores';

function getToken(): string {
  return String(useAccessStore().accessToken);
}

import { useRagFileManager } from '../composables/useRagFileManager';
import RagRenameDialog from './RagRenameDialog.vue';
import FilePreviewDialog from '#/components/FilePreviewDialog.vue';

const props = defineProps<{
  fm: ReturnType<typeof useRagFileManager>;
  creatorId?: string;
}>();

const router = useRouter();

const {
  currentFolderId,
  viewMode,
  fileList,
  loading,
  selectedFileIds,
  navigateToFolder,
  fetchFiles,
  clearSelection,
} = props.fm;

type ViewItem = RagFileApi.FileItem & {
  kbId?: string;
  type?: string;
  file_type?: string;
  file_ext?: string;
  fileExt?: string;
  fileSize?: number;
  size?: number;
  storagePath?: string;
  path?: string;
};

const renameDialogVisible = ref(false);
const previewDialogRef = ref<InstanceType<typeof FilePreviewDialog>>();
const currentItem = ref<ViewItem | null>(null);
const tableRef = ref<InstanceType<typeof ElTable>>();
const previewVisible = ref(false);
const previewUrlList = ref<string[]>([]);
const previewInitialIndex = ref(0);

const isAllSelected = computed(() => {
  return (
    fileList.value.length > 0 &&
    selectedFileIds.value.size === fileList.value.length
  );
});

const isIndeterminate = computed(() => {
  return (
    selectedFileIds.value.size > 0 &&
    selectedFileIds.value.size < fileList.value.length
  );
});

const handleSelectAll = (val: boolean | string | number) => {
  if (val) {
    fileList.value.forEach((item) => selectedFileIds.value.add(item.id!));
    if (viewMode.value === 'list' && tableRef.value) {
      tableRef.value.toggleAllSelection();
    }
  } else {
    clearSelection();
    if (viewMode.value === 'list' && tableRef.value) {
      tableRef.value.clearSelection();
    }
  }
};

watch(currentFolderId, () => {
  clearSelection();
  fetchFiles(props.creatorId);
});

onMounted(() => fetchFiles(props.creatorId));

const handleSelectionChange = (selection: ViewItem[]) => {
  selectedFileIds.value.clear();
  selection.forEach((item) => item.id && selectedFileIds.value.add(item.id));
};

const handleGridSelect = (id: string | undefined, value: boolean) => {
  if (!id) return;
  if (value) {
    selectedFileIds.value.add(id);
  } else {
    selectedFileIds.value.delete(id);
  }
};

const isImage = (ext?: string) => {
  if (!ext) return false;
  const extension = ext.toLowerCase().replace('.', '');
  return ['bmp', 'gif', 'jpeg', 'jpg', 'png', 'svg', 'webp'].includes(extension);
};

const getFileIcon = (type: string, ext?: string) => {
  if (type === 'folder') return Folder;
  if (!ext) return FileText;
  const extension = ext.toLowerCase().replace('.', '');
  if (['bmp', 'gif', 'jpeg', 'jpg', 'png', 'svg', 'webp'].includes(extension)) return FileImage;
  if (['avi', 'mkv', 'mov', 'mp4', 'webm'].includes(extension)) return FileVideo;
  if (['flac', 'mp3', 'ogg', 'wav'].includes(extension)) return FileAudio;
  if (['7z', 'gz', 'rar', 'tar', 'zip'].includes(extension)) return FileArchive;
  return FileText;
};

const thumbUrl = (item: ViewItem) => {
  if (item.kbId && item.id) return getKbFileStreamUrl(item.id, item.kbId, getToken());
  if (item.id) return getFileStreamUrl(item.id, getToken());
  return '';
};

function getItemType(item: ViewItem): string {
  return item.fileType || item.file_type || item.type || '';
}

function getItemExt(item: ViewItem): string {
  return item.fileExt || item.file_ext || '';
}

const handleItemClick = (item: ViewItem) => {
  const type = getItemType(item);
  if (type === 'folder') {
    navigateToFolder(item.id ?? null, item.name);
  } else if (isImage(getItemExt(item))) {
    const images = fileList.value.filter((f) => isImage(getItemExt(f)));
    if (item.kbId) {
      previewUrlList.value = images.map((img) => {
        return getKbFileStreamUrl(img.id!, img.kbId!, getToken());
      });
    } else {
      previewUrlList.value = images.map((img) => getFileStreamUrl(img.id!, getToken()));
    }
    const index = images.findIndex((img) => img.id === item.id);
    previewInitialIndex.value = index === -1 ? 0 : index;
    previewVisible.value = true;
  } else if (item.kbId) {
    router.push(`/rag/kb-file/${item.id}/task?kbId=${item.kbId}`);
  } else if (['pdf', 'docx'].includes(getItemExt(item).toLowerCase().replace('.', ''))) {
    router.push(`/rag/file-manager/${item.id}/task`);
  } else {
    previewDialogRef.value?.open(item);
  }
};

const closePreview = () => {
  previewVisible.value = false;
};

const handleDownload = (item: ViewItem) => {
  const type = getItemType(item);
  if (type === 'folder') {
    ElMessage.warning($t('file-manager.folderDownloadNotSupported'));
    return;
  }
  const url = getDownloadUrl(item.storagePath || item.path || '', getToken());
  window.open(url, '_blank');
};

const handleDelete = async (item: ViewItem) => {
  try {
    await ElMessageBox.confirm(
      $t('file-manager.deleteConfirm', { name: item.name }),
      $t('file-manager.tip'),
      {
        type: 'warning',
        confirmButtonText: $t('file-manager.confirm'),
        cancelButtonText: $t('file-manager.cancel'),
      },
    );
    await deleteItem(item.id!);
    ElMessage.success($t('file-manager.deleteSuccess'));
    fetchFiles(props.creatorId);
  } catch (error) {
    if (error !== 'cancel') {
      console.error(error);
    }
  }
};

const openRenameDialog = (item: ViewItem) => {
  currentItem.value = item;
  renameDialogVisible.value = true;
};

const handleAction = (action: string, item: ViewItem) => {
  switch (action) {
    case 'delete': handleDelete(item); break;
    case 'download': handleDownload(item); break;
    case 'open': handleItemClick(item); break;
    case 'rename': openRenameDialog(item); break;
  }
};

const formatSize = (size?: number) => {
  if (size === undefined || size === null) return '-';
  if (size === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  let s = size;
  while (s >= 1024 && i < units.length - 1) {
    s /= 1024;
    i++;
  }
  return `${s.toFixed(2)} ${units[i]}`;
};
</script>

<template>
  <div v-loading="loading" class="h-full w-full overflow-y-auto">
    <div
      v-if="fileList.length === 0 && !loading"
      class="flex h-full items-center justify-center"
    >
      <ElEmpty :description="$t('file-manager.noFiles')" />
    </div>

    <template v-else-if="viewMode === 'grid'">
      <div class="bg-background sticky top-0 z-20 flex items-center px-4 py-2">
        <ElCheckbox
          :model-value="isAllSelected"
          :indeterminate="isIndeterminate"
          @change="handleSelectAll"
        >
          {{ $t('file-manager.selectAll') }} {{ selectedFileIds.size > 0 ? `(${selectedFileIds.size})` : '' }}
        </ElCheckbox>
      </div>
      <div class="grid grid-cols-2 gap-4 px-4 py-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
        <div
          v-for="item in fileList"
          :key="item.id"
          class="border-border bg-card hover:bg-accent group relative flex cursor-pointer flex-col rounded-lg border p-4 transition-colors"
          :class="{
            'ring-primary bg-accent ring-2': selectedFileIds.has(item.id!),
          }"
          @click="handleItemClick(item)"
        >
          <div class="absolute left-2 top-2 z-10" @click.stop>
            <ElCheckbox
              :model-value="selectedFileIds.has(item.id!)"
              @change="(val: boolean) => handleGridSelect(item.id, val)"
            />
          </div>

          <div class="absolute right-2 top-2 z-10" @click.stop>
            <ElDropdown trigger="click">
              <button class="invisible rounded-full p-1 hover:bg-gray-200 group-hover:visible dark:hover:bg-gray-700">
                <MoreVertical class="size-4 text-gray-500" />
              </button>
              <template #dropdown>
                <ElDropdownMenu>
                  <ElDropdownItem @click="handleAction('open', item)">{{ $t('file-manager.open') }}</ElDropdownItem>
                  <ElDropdownItem @click="handleAction('download', item)">{{ $t('file-manager.download') }}</ElDropdownItem>
                  <ElDropdownItem divided @click="handleAction('rename', item)">{{ $t('file-manager.rename') }}</ElDropdownItem>
                  <ElDropdownItem class="text-red-500" @click="handleAction('delete', item)">{{ $t('file-manager.delete') }}</ElDropdownItem>
                </ElDropdownMenu>
              </template>
            </ElDropdown>
          </div>

          <div class="flex flex-1 items-center justify-center overflow-hidden py-4">
            <img
              v-if="isImage(item.fileExt)"
              :src="thumbUrl(item)"
              class="h-16 w-full object-contain"
              loading="lazy"
            />
            <component
              v-else
              :is="getFileIcon(item.fileType || item.file_type || item.type, item.fileExt)"
              class="size-16"
              :class="(item.fileType || item.file_type || item.type) === 'folder' ? 'text-blue-500' : 'text-gray-500'"
            />
          </div>
          <div class="px-2 text-center">
            <span class="block truncate text-sm font-medium" :title="item.name">{{ item.name }}</span>
          </div>
        </div>
      </div>
    </template>

    <div v-else class="h-full px-4 py-2">
      <ElTable
        ref="tableRef"
        :data="fileList"
        style="width: 100%"
        row-class-name="file-list-row"
        @row-click="handleItemClick"
        @selection-change="handleSelectionChange"
      >
        <ElTableColumn type="selection" width="50" />
        <ElTableColumn width="60">
          <template #default="{ row }">
            <img
              v-if="isImage(row.fileExt)"
              :src="thumbUrl(row)"
              class="size-5 rounded object-cover"
              loading="lazy"
            />
            <component
              v-else
              :is="getFileIcon(row.fileType || row.file_type || row.type, row.fileExt)"
              class="size-5"
              :class="(row.fileType || row.file_type || row.type) === 'folder' ? 'text-blue-500' : 'text-gray-500'"
            />
          </template>
        </ElTableColumn>
        <ElTableColumn prop="name" :label="$t('file-manager.name')" min-width="200" sortable />
        <ElTableColumn prop="fileSize" :label="$t('file-manager.size')" width="120">
          <template #default="{ row }">
            {{ (row.fileType || row.file_type || row.type) === 'folder' ? '-' : formatSize(row.fileSize || row.size) }}
          </template>
        </ElTableColumn>
        <ElTableColumn prop="updatedTime" :label="$t('file-manager.modifiedTime')" width="180">
          <template #default="{ row }">
            {{ row.updatedTime?.substring(0, 16) }}
          </template>
        </ElTableColumn>
        <ElTableColumn :label="$t('file-manager.actions')" width="80" fixed="right">
          <template #default="{ row }">
            <ElDropdown trigger="click">
              <button class="rounded p-1 hover:bg-gray-100 dark:hover:bg-gray-700" @click.stop>
                <MoreVertical class="size-4" />
              </button>
              <template #dropdown>
                <ElDropdownMenu>
                  <ElDropdownItem @click="handleAction('open', row)">{{ $t('file-manager.open') }}</ElDropdownItem>
                  <ElDropdownItem @click="handleAction('download', row)">{{ $t('file-manager.download') }}</ElDropdownItem>
                  <ElDropdownItem divided @click="handleAction('rename', row)">{{ $t('file-manager.rename') }}</ElDropdownItem>
                  <ElDropdownItem class="text-red-500" @click="handleAction('delete', row)">{{ $t('file-manager.delete') }}</ElDropdownItem>
                </ElDropdownMenu>
              </template>
            </ElDropdown>
          </template>
        </ElTableColumn>
      </ElTable>
    </div>

    <RagRenameDialog
      v-model:visible="renameDialogVisible"
      :item="currentItem"
      :fm="fm"
    />

    <FilePreviewDialog ref="previewDialogRef" />

    <ImageViewer
      v-if="previewVisible"
      :url-list="previewUrlList"
      :initial-index="previewInitialIndex"
      @close="closePreview"
    />
  </div>
</template>

<style scoped>
:deep(.el-table__row td) {
  padding: 16px 0;
  border-bottom: none !important;
}

:deep(.el-table__inner-wrapper::before) {
  display: none;
}

:deep(.el-table__header th.el-table__cell) {
  border-bottom: none !important;
}
</style>
