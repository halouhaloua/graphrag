<script setup lang="ts">
import { ref, computed } from 'vue';
import { Page } from '@vben/common-ui';
import { Database, Folder } from '@vben/icons';
import { $t } from '@vben/locales';
import { useUserStore } from '@vben/stores';

import { useRagFileManager } from './composables/useRagFileManager';
import { useKbFileManager } from './composables/useKbFileManager';
import RagFolderTree from './components/RagFolderTree.vue';
import KbFolderTree from './components/KbFolderTree.vue';
import RagFileToolbar from './components/RagFileToolbar.vue';
import KbFileToolbar from './components/KbFileToolbar.vue';
import RagFileList from './components/RagFileList.vue';
import RagCreateFolderDialog from './components/RagCreateFolderDialog.vue';

const userStore = useUserStore();
const creatorId = computed(() => userStore.userInfo?.userId);

const activeScope = ref<'personal' | 'shared' | 'kb'>('personal');

const personalFm = useRagFileManager('personal');
const sharedFm = useRagFileManager('shared');
const kbFm = useKbFileManager();

const ragFm = computed(() =>
  activeScope.value === 'personal' ? personalFm : sharedFm,
);
</script>

<template>
  <Page auto-content-height>
    <div class="flex h-full w-full gap-3">
      <!-- 左栏 -->
      <div class="bg-background flex h-full w-64 flex-col rounded-[10px]">
        <div class="text-foreground flex items-center gap-2 p-4 text-sm font-bold">
          <Folder class="text-primary size-5" />
          {{ $t('file-manager.fileManagement') }}
        </div>

        <!-- Scope 切换区 -->
        <div class="mx-2 mb-1 flex flex-col gap-0.5 rounded-lg bg-background p-1">
          <div
            class="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors"
            :class="activeScope === 'personal'
              ? 'bg-accent text-primary font-medium'
              : 'hover:bg-accent'"
            @click="activeScope = 'personal'"
          >
            <Folder class="size-4" />
            个人资料
          </div>
          <div
            class="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors"
            :class="activeScope === 'shared'
              ? 'bg-accent text-primary font-medium'
              : 'hover:bg-accent'"
            @click="activeScope = 'shared'"
          >
            <Folder class="size-4" />
            共建资料
          </div>
          <div
            class="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors"
            :class="activeScope === 'kb'
              ? 'bg-accent text-primary font-medium'
              : 'hover:bg-accent'"
            @click="activeScope = 'kb'; kbFm.navigateToFolder(null)"
          >
            <Database class="size-4" />
            知识库资料
          </div>
        </div>

        <!-- 文件夹树 -->
        <RagFolderTree v-if="activeScope === 'personal'" :fm="personalFm" />
        <RagFolderTree v-if="activeScope === 'shared'" :fm="sharedFm" />
        <KbFolderTree v-if="activeScope === 'kb'" :fm="kbFm" />
      </div>

      <!-- 右栏 -->
      <div
        :key="activeScope"
        class="bg-background flex flex-1 flex-col overflow-hidden rounded-[10px]"
      >
        <template v-if="activeScope !== 'kb'">
          <RagFileToolbar :fm="ragFm" :creator-id="creatorId" />
          <div class="flex-1 overflow-hidden">
            <RagFileList :fm="ragFm" :creator-id="creatorId" />
          </div>
        </template>
        <template v-else>
          <KbFileToolbar :fm="kbFm" />
          <div class="flex-1 overflow-hidden">
            <RagFileList :fm="kbFm as any" />
          </div>
        </template>
      </div>

      <RagCreateFolderDialog v-if="activeScope !== 'kb'" :fm="ragFm" :creator-id="creatorId" />
    </div>
  </Page>
</template>
