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
  ElOption,
  ElSelect,
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
  (e: 'success', newId?: string): void;
}>();

const visible = ref(false);
const submitting = ref(false);

const form = reactive({
  name: '',
  description: '',
  workflowType: 'ai_workflow',
  workflowRoute: '',
});

const formRef = ref<InstanceType<typeof ElForm>>();

watch(
  () => props.modelValue,
  (val) => {
    visible.value = val;
    if (val && props.workflow) {
      form.name = props.workflow.name;
      form.description = props.workflow.description || '';
      form.workflowType = props.workflow.workflow_type || 'ai_workflow';
      form.workflowRoute = props.workflow.workflow_route || '';
    } else if (val) {
      form.name = '';
      form.description = '';
      form.workflowType = 'ai_workflow';
      form.workflowRoute = '';
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
        workflow_type: form.workflowType,
        workflow_route: form.workflowRoute || undefined,
      });
      ElMessage.success('已更新');
      visible.value = false;
      emit('success');
    } else {
      const result = await createWorkflowDefApi({
        name: form.name,
        description: form.description || undefined,
        workflow_type: form.workflowType,
        workflow_route: form.workflowRoute || undefined,
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
      
      <ElFormItem label="类型" prop="workflowType">
        <ElSelect v-model="form.workflowType" placeholder="选择工作流类型">
          <ElOption label="AI 工作流" value="ai_workflow" />
          <ElOption label="应用工作流" value="app_workflow" />
        </ElSelect>
        <div class="form-field-hint">
          AI 工作流适用于对话式交互；应用工作流适用于固定流程任务。
        </div>
      </ElFormItem>

      <ElFormItem label="访问路由" prop="workflowRoute">
        <ElInput v-model="form.workflowRoute" placeholder="留空则发布时自动生成">
          <template #prepend>
            /wf/{{ form.workflowType === 'ai_workflow' ? 'ai' : 'app' }}/
          </template>
        </ElInput>
        <div class="form-field-hint">
          支持英文、数字、中划线，发布后将通过此路径访问。不填则发布时自动根据名称生成。
        </div>
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

<style scoped>
.form-field-hint {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  margin-top: 4px;
  line-height: 1.4;
}
</style>
