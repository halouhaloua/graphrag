<script setup lang="ts">
import type { WorkflowDef } from '#/api/core/ai-workflow';

import { reactive, ref, watch } from 'vue';

import {
  ElButton,
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElMessage,
} from 'element-plus';

import {
  createWorkflowDefApi,
  updateWorkflowDefApi,
} from '#/api/core/ai-workflow';

const props = defineProps<{
  modelValue: boolean;
  workflow?: WorkflowDef | null;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void;
  (e: 'success'): void;
}>();

const visible = ref(false);
const submitting = ref(false);

const form = reactive({
  name: '',
  description: '',
});

const formRef = ref<InstanceType<typeof ElForm>>();

watch(
  () => props.modelValue,
  (val) => {
    visible.value = val;
    if (val && props.workflow) {
      form.name = props.workflow.name;
      form.description = props.workflow.description || '';
    } else if (val) {
      form.name = '';
      form.description = '';
    }
  },
);

watch(visible, (val) => {
  emit('update:modelValue', val);
});

const handleSave = async () => {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;

  submitting.value = true;
  try {
    if (props.workflow) {
      await updateWorkflowDefApi(props.workflow.id, {
        name: form.name,
        description: form.description || undefined,
      });
      ElMessage.success('已更新');
      visible.value = false;
      emit('success');
    } else {
      const result = await createWorkflowDefApi({
        name: form.name,
        description: form.description || undefined,
        nodes: [],
        edges: [],
      });
      ElMessage.success('已创建');
      visible.value = false;
      emit('success', result.id);
    }
  } catch {
    ElMessage.error('保存失败');
  } finally {
    submitting.value = false;
  }
};
</script>

<template>
  <ElDialog
    :model-value="visible"
    :title="workflow ? '编辑工作流' : '创建工作流'"
    width="600px"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <ElForm ref="formRef" :model="form" label-width="80px">
      <ElFormItem
        label="名称"
        prop="name"
        :rules="[{ required: true, message: '请输入工作流名称', trigger: 'blur' }]"
      >
        <ElInput
          v-model="form.name"
          placeholder="请输入工作流名称"
          maxlength="200"
        />
      </ElFormItem>
      <ElFormItem label="描述" prop="description">
        <ElInput
          v-model="form.description"
          type="textarea"
          :rows="4"
          placeholder="请输入工作流描述（可选）"
        />
      </ElFormItem>
    </ElForm>
    <template #footer>
      <ElButton @click="visible = false">取消</ElButton>
      <ElButton type="primary" :loading="submitting" @click="handleSave">
        保存
      </ElButton>
    </template>
  </ElDialog>
</template>
