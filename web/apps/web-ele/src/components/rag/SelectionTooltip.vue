<script lang="ts" setup>
import { onBeforeUnmount, onMounted, ref } from 'vue';
import {
  ElButton,
  ElDialog,
  ElInput,
  ElMessage,
} from 'element-plus';

const props = defineProps<{
  editor: any;
  processing: boolean;
}>();

const emit = defineEmits<{
  polish: [];
  rewrite: [];
  custom: [prompt: string];
}>();

const visible = ref(false);
const tooltipStyle = ref<Record<string, string>>({});
const showCustomDialog = ref(false);
const customPrompt = ref('');

function updatePosition() {
  if (props.processing) {
    visible.value = false;
    return;
  }

  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || !sel.rangeCount) {
    visible.value = false;
    return;
  }

  const editorDom = props.editor?.view.dom;
  if (!editorDom) {
    visible.value = false;
    return;
  }

  const isInEditor =
    editorDom.contains(sel.anchorNode) &&
    editorDom.contains(sel.focusNode);
  if (!isInEditor) {
    visible.value = false;
    return;
  }

  const range = sel.getRangeAt(0);
  const rect = range.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) {
    visible.value = false;
    return;
  }

  tooltipStyle.value = {
    position: 'fixed',
    left: `${rect.left + rect.width / 2}px`,
    top: `${rect.top - 8}px`,
    transform: 'translate(-50%, -100%)',
  };
  visible.value = true;
}

function onSelectionChange() {
  updatePosition();
}

function handlePolish() {
  visible.value = false;
  emit('polish');
}

function handleRewrite() {
  visible.value = false;
  emit('rewrite');
}

function handleCustom() {
  visible.value = false;
  showCustomDialog.value = true;
}

function confirmCustom() {
  const prompt = customPrompt.value.trim();
  if (!prompt) {
    ElMessage.warning('请输入指令');
    return;
  }
  showCustomDialog.value = false;
  emit('custom', prompt);
  customPrompt.value = '';
}

onMounted(() => {
  document.addEventListener('selectionchange', onSelectionChange);
});

onBeforeUnmount(() => {
  document.removeEventListener('selectionchange', onSelectionChange);
});
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="visible" class="selection-tooltip" :style="tooltipStyle">
        <ElButton size="small" @click="handlePolish">✨ 润色</ElButton>
        <ElButton size="small" @click="handleRewrite">✏️ 改写</ElButton>
        <ElButton size="small" @click="handleCustom">🛠 自定义</ElButton>
        <div class="tooltip-arrow" />
      </div>
    </Transition>

    <ElDialog
      v-model="showCustomDialog"
      title="自定义 AI 指令"
      width="420px"
      :close-on-click-modal="false"
    >
      <ElInput
        v-model="customPrompt"
        type="textarea"
        :rows="3"
        placeholder="输入您的要求，例如「使文章更正式」「简化语言」「转换为口语化表达」"
      />
      <template #footer>
        <ElButton @click="showCustomDialog = false">取消</ElButton>
        <ElButton type="primary" @click="confirmCustom">确认</ElButton>
      </template>
    </ElDialog>
  </Teleport>
</template>

<style scoped>
.selection-tooltip {
  display: flex;
  gap: 4px;
  align-items: center;
  padding: 4px 6px;
  background: var(--el-bg-color-overlay);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgb(0 0 0 / 12%);
  z-index: 9999;
  pointer-events: auto;
}

.tooltip-arrow {
  position: absolute;
  bottom: -5px;
  left: 50%;
  width: 8px;
  height: 8px;
  background: var(--el-bg-color-overlay);
  border-right: 1px solid var(--el-border-color-lighter);
  border-bottom: 1px solid var(--el-border-color-lighter);
  transform: translateX(-50%) rotate(45deg);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
