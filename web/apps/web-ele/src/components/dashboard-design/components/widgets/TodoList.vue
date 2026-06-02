<script setup lang="ts">
import type { DashboardWidget } from '../../store/dashboardDesignStore';

import { inject, ref } from 'vue';

import { CheckSquare } from '@vben/icons';
import { $t } from '@vben/locales';

import {
  ElButton,
  ElCheckbox,
  ElInput,
  ElScrollbar,
  ElTag,
} from 'element-plus';

import { useDashboardDesignStore } from '../../store/dashboardDesignStore';

const props = defineProps<{
  widget: DashboardWidget;
}>();

const store = useDashboardDesignStore();

const updateWidgetProps =
  inject<((id: string, p: Record<string, any>) => void) | null>(
    'updateWidgetProps',
    null,
  ) || store.updateWidgetProps;

const getPriorityType = (priority: string) => {
  switch (priority) {
    case 'high': {
      return 'danger';
    }
    case 'low': {
      return 'info';
    }
    case 'medium': {
      return 'warning';
    }
    default: {
      return 'info';
    }
  }
};

const getPriorityLabel = (priority: string) => {
  switch (priority) {
    case 'high': {
      return $t('dashboard-design.widgets.todo.priority.high');
    }
    case 'low': {
      return $t('dashboard-design.widgets.todo.priority.low');
    }
    case 'medium': {
      return $t('dashboard-design.widgets.todo.priority.medium');
    }
    default: {
      return priority;
    }
  }
};

const priorityCycle: Record<string, string> = {
  high: 'medium',
  medium: 'low',
  low: 'high',
};

const editingId = ref<null | string>(null);
const editValue = ref('');

const toggleDone = (item: any) => {
  const items = props.widget.props.items.map((i: any) =>
    i.id === item.id ? { ...i, done: !i.done } : i,
  );
  updateWidgetProps(props.widget.id, { items });
};

const cyclePriority = (item: any) => {
  const nextPriority = priorityCycle[item.priority] || 'medium';
  const items = props.widget.props.items.map((i: any) =>
    i.id === item.id ? { ...i, priority: nextPriority } : i,
  );
  updateWidgetProps(props.widget.id, { items });
};

const deleteItem = (item: any) => {
  const items = props.widget.props.items.filter((i: any) => i.id !== item.id);
  updateWidgetProps(props.widget.id, { items });
};

const addItem = () => {
  const items = [...(props.widget.props.items || [])];
  items.push({
    id: String(Date.now()),
    title: $t('dashboard-design.attribute.widget.todo.newItem'),
    done: false,
    priority: 'medium',
  });
  updateWidgetProps(props.widget.id, { items });
};

const startEdit = (item: any) => {
  editingId.value = item.id;
  editValue.value = item.title;
};

const saveEdit = () => {
  if (editingId.value) {
    const items = props.widget.props.items.map((i: any) =>
      i.id === editingId.value ? { ...i, title: editValue.value } : i,
    );
    updateWidgetProps(props.widget.id, { items });
  }
  editingId.value = null;
};
</script>

<template>
  <div class="todo-list flex h-full flex-col p-3">
    <div class="mb-3 flex items-center gap-2">
      <CheckSquare class="text-muted-foreground h-4 w-4" />
      <span class="text-muted-foreground text-sm font-medium">{{
        widget.props.title
      }}</span>
    </div>
    <ElScrollbar class="flex-1">
      <div class="space-y-2">
        <div
          v-for="item in widget.props.items"
          :key="item.id"
          class="group flex items-center gap-2 rounded-md p-2 transition-colors hover:bg-gray-50 dark:hover:bg-gray-800"
        >
          <ElCheckbox
            :model-value="item.done"
            size="small"
            @change="toggleDone(item)"
          />
          <template v-if="editingId === item.id">
            <ElInput
              v-model="editValue"
              size="small"
              @keyup.enter="saveEdit"
              @blur="saveEdit"
              autofocus
            />
          </template>
          <span
            v-else
            class="flex-1 cursor-text text-sm"
            :class="{ 'text-muted-foreground line-through': item.done }"
            @dblclick="startEdit(item)"
          >
            {{ item.title }}
          </span>
          <ElTag
            :type="getPriorityType(item.priority)"
            size="small"
            class="cursor-pointer"
            @click="cyclePriority(item)"
          >
            {{ getPriorityLabel(item.priority) }}
          </ElTag>
          <span
            class="delete-btn cursor-pointer text-gray-400 opacity-0 transition-opacity hover:text-red-500 group-hover:opacity-100"
            @click="deleteItem(item)"
          >
            ×
          </span>
        </div>
      </div>
    </ElScrollbar>
    <div class="mt-2 flex items-center gap-2">
      <ElButton size="small" type="primary" @click="addItem">
        + {{ $t('dashboard-design.attribute.widget.todo.add') }}
      </ElButton>
    </div>
  </div>
</template>

<style scoped>
/* 背景色由 WidgetRenderer 控制 */
</style>
