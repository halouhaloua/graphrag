<script setup lang="ts">
import type { DashboardWidget } from '../../store/dashboardDesignStore';

import { ref } from 'vue';

import { Calendar } from '@vben/icons';

import { ElCalendar } from 'element-plus';

defineProps<{
  widget: DashboardWidget;
}>();

const selectedDate = ref(new Date());
</script>

<template>
  <div class="calendar-widget flex h-full flex-col p-3">
    <div class="mb-2 flex items-center gap-2">
      <Calendar class="text-muted-foreground h-4 w-4" />
      <span class="text-muted-foreground text-sm font-medium">{{
        widget.props.title
      }}</span>
    </div>
    <div class="min-h-0 flex-1 overflow-hidden">
      <ElCalendar v-model="selectedDate" class="compact-calendar" />
    </div>
  </div>
</template>

<style scoped>
.compact-calendar {
  --el-calendar-border: none;
}

:deep(.el-calendar) {
  height: 100%;
}

:deep(.el-calendar__header) {
  padding: 8px 0;
}

:deep(.el-calendar__body) {
  padding: 0;
}

:deep(.el-calendar-table thead th) {
  padding: 4px 0;
  font-size: 12px;
}

/* 合并所有 .el-calendar-day 的样式 */
:deep(.el-calendar-table .el-calendar-day) {
  height: 32px;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  box-sizing: border-box;
}

:deep(.el-calendar-table td) {
  text-align: center;
}

:deep(.el-calendar-table td.is-today .el-calendar-day) {
  font-weight: bold;
  color: var(--el-color-primary);
}

/* 合并选中和悬浮的圆形样式 */
:deep(.el-calendar-table td.is-selected .el-calendar-day),
:deep(.el-calendar-table .el-calendar-day:hover) {
  background-color: #e5e7eb !important;
  border-radius: 50% !important;
  width: 32px;
  height: 32px;
  margin: 0 auto;
  color: #1f2937 !important;
}

:deep(.el-calendar-table td:hover) {
  background-color: transparent !important;
}

:deep(.el-calendar-table td.is-selected) {
  background-color: transparent !important;
}
</style>