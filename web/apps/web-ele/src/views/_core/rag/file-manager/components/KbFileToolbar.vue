<script setup lang="ts">
import { ChevronRight, Home, LayoutGrid, List, RefreshCw, Search } from '@vben/icons';
import { ElBreadcrumb, ElBreadcrumbItem, ElButton, ElInput } from 'element-plus';

import { useKbFileManager } from '../composables/useKbFileManager';

const props = defineProps<{
  fm: ReturnType<typeof useKbFileManager>;
}>();

const { viewMode, breadcrumbs, searchQuery, navigateToFolder, fetchFiles } =
  props.fm;

const handleBreadcrumbClick = (id: null | string, name: string) => {
  navigateToFolder(id, name);
};
</script>

<template>
  <div class="border-border flex items-center justify-between border-b px-4 py-3">
    <div class="mr-4 flex flex-1 items-center overflow-hidden">
      <ElBreadcrumb :separator-icon="ChevronRight">
        <ElBreadcrumbItem
          v-for="(item, index) in breadcrumbs"
          :key="item.id || 'root'"
        >
          <span
            class="hover:text-primary flex cursor-pointer items-center gap-1"
            :class="{
              'text-foreground font-bold': index === breadcrumbs.length - 1,
            }"
            @click="handleBreadcrumbClick(item.id, item.name)"
          >
            <Home v-if="index === 0" class="size-4" />
            {{ item.name }}
          </span>
        </ElBreadcrumbItem>
      </ElBreadcrumb>
    </div>

    <div class="flex flex-shrink-0 items-center gap-2 sm:gap-3">
      <ElInput v-model="searchQuery" placeholder="搜索文件..." class="w-32 sm:w-48">
        <template #prefix>
          <Search class="size-4" />
        </template>
      </ElInput>

      <div class="flex items-center rounded-lg border p-1">
        <button
          class="hover:bg-accent p-2"
          :class="{ 'bg-accent text-primary': viewMode === 'list' }"
          @click="viewMode = 'list'"
          title="列表视图"
        >
          <List class="size-4" />
        </button>
        <button
          class="hover:bg-accent p-2"
          :class="{ 'bg-accent text-primary': viewMode === 'grid' }"
          @click="viewMode = 'grid'"
          title="网格视图"
        >
          <LayoutGrid class="size-4" />
        </button>
      </div>

      <ElButton circle @click="fetchFiles()">
        <RefreshCw class="size-4" />
      </ElButton>
    </div>
  </div>
</template>
