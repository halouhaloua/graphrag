<script setup lang="ts">
import type { TeamConfig, TeamRoleDef } from '#/api/core/ai-workflow';

import { reactive, ref, watch } from 'vue';

import { Plus, X } from '@vben/icons';

import {
  ElButton,
  ElCheckbox,
  ElCheckboxGroup,
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElMessage,
  ElSelect,
  ElOption,
} from 'element-plus';

import {
  createTeamApi,
  updateTeamApi,
} from '#/api/core/ai-workflow';

interface RoleFormItem {
  key: string;
  agentDescription: string;
  modelName: string;
  maxIterations: number;
  tools: string[];
}

const props = defineProps<{
  modelValue: boolean;
  team?: TeamConfig | null;
  nodeTypes: { type: string; name: string }[];
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
  teamRules: '',
  startRole: '',
  roles: [] as RoleFormItem[],
});

const formRef = ref<InstanceType<typeof ElForm>>();

watch(
  () => props.modelValue,
  (val) => {
    visible.value = val;
    if (val && props.team) {
      form.name = props.team.name;
      form.description = props.team.description || '';
      form.teamRules = props.team.team_rules;
      form.startRole = props.team.start_role;
      form.roles = Object.entries(props.team.roles || {}).map(
        ([key, role]) => ({
          key,
          agentDescription: (role as TeamRoleDef).agent_description || '',
          modelName: (role as TeamRoleDef).model_name || 'deepseek-chat',
          maxIterations: (role as TeamRoleDef).max_iterations ?? 25,
          tools: (role as TeamRoleDef).tools || [],
        }),
      );
    } else if (val) {
      form.name = '';
      form.description = '';
      form.teamRules = '你们是一个出色的团队，致力于合作完成艰巨的工作。';
      form.startRole = '';
      form.roles = [];
    }
  },
);

watch(visible, (val) => {
  emit('update:modelValue', val);
});

function addRole() {
  const idx = form.roles.length + 1;
  form.roles.push({
    key: `新角色${idx}`,
    agentDescription: '',
    modelName: 'deepseek-chat',
    maxIterations: 25,
    tools: [],
  });
  if (!form.startRole) {
    form.startRole = `新角色${idx}`;
  }
}

function removeRole(index: number) {
  const removed = form.roles[index];
  if (!removed) return;
  form.roles.splice(index, 1);
  if (form.startRole === removed.key) {
    form.startRole = form.roles[0]?.key || '';
  }
}

function onRoleKeyChange(oldKey: string, newKey: string) {
  if (form.startRole === oldKey) {
    form.startRole = newKey;
  }
}

const availableNodeTypes = computed(() => {
  return (props.nodeTypes || []).filter(
    (n) => n.type && !['_start', '_end', 'handoff', 'final_answer'].includes(n.type),
  );
});

import { computed } from 'vue';

const handleSave = async () => {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;
  if (form.roles.length === 0) {
    ElMessage.warning('请至少添加一个角色');
    return;
  }
  if (!form.startRole) {
    ElMessage.warning('请选择起始角色');
    return;
  }
  if (!form.roles.find((r) => r.key === form.startRole)) {
    ElMessage.warning('起始角色必须存在于角色列表中');
    return;
  }

  submitting.value = true;
  try {
    const rolesDict: Record<string, TeamRoleDef> = {};
    for (const r of form.roles) {
      rolesDict[r.key] = {
        agent_description: r.agentDescription || undefined,
        model_name: r.modelName,
        max_iterations: r.maxIterations,
        tools: r.tools,
        termination_conditions: [],
      };
    }

    if (props.team) {
      await updateTeamApi(props.team.id, {
        name: form.name,
        description: form.description || undefined,
        team_rules: form.teamRules,
        start_role: form.startRole,
        roles: rolesDict,
      });
      ElMessage.success('已更新');
      visible.value = false;
      emit('success');
    } else {
      const result = await createTeamApi({
        name: form.name,
        description: form.description || undefined,
        team_rules: form.teamRules,
        start_role: form.startRole,
        roles: rolesDict,
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
    :title="team ? '编辑团队' : '创建团队'"
    width="700px"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <ElForm ref="formRef" :model="form" label-width="80px">
      <ElFormItem
        label="名称"
        prop="name"
        :rules="[{ required: true, message: '请输入团队名称', trigger: 'blur' }]"
      >
        <ElInput v-model="form.name" placeholder="请输入团队名称" maxlength="200" />
      </ElFormItem>

      <ElFormItem label="描述" prop="description">
        <ElInput v-model="form.description" type="textarea" :rows="2" placeholder="可选" />
      </ElFormItem>

      <ElFormItem
        label="团队规则"
        prop="teamRules"
        :rules="[{ required: true, message: '请输入团队规则', trigger: 'blur' }]"
      >
        <ElInput v-model="form.teamRules" type="textarea" :rows="3" placeholder="定义团队协作规则和目标" />
      </ElFormItem>

      <ElFormItem label="起始角色" prop="startRole">
        <ElSelect v-model="form.startRole" placeholder="选择起始角色">
          <ElOption
            v-for="r in form.roles"
            :key="r.key"
            :label="r.key"
            :value="r.key"
          />
        </ElSelect>
      </ElFormItem>

      <!-- 角色列表 -->
      <div class="roles-section">
        <div class="roles-section__header">
          <span class="roles-section__title">角色列表</span>
          <ElButton size="small" type="primary" plain @click="addRole">
            <Plus class="mr-1 h-3.5 w-3.5" />
            添加角色
          </ElButton>
        </div>

        <div
          v-for="(role, index) in form.roles"
          :key="index"
          class="role-card"
        >
          <div class="role-card__header">
            <span class="role-card__index">#{{ index + 1 }}</span>
            <ElButton
              text
              size="small"
              type="danger"
              @click="removeRole(index)"
            >
              <X class="h-3.5 w-3.5" />
            </ElButton>
          </div>

          <div class="role-card__body">
            <div class="role-row">
              <div class="role-field role-field--name">
                <label>名称</label>
                <ElInput
                  v-model="role.key"
                  size="small"
                  placeholder="角色名称"
                  @update:model-value="onRoleKeyChange(role.key, $event)"
                />
              </div>
              <div class="role-field role-field--model">
                <label>模型</label>
                <ElInput
                  v-model="role.modelName"
                  size="small"
                  placeholder="deepseek-chat"
                />
              </div>
              <div class="role-field role-field--iters">
                <label>轮数</label>
                <ElInputNumber
                  v-model="role.maxIterations"
                  size="small"
                  :min="1"
                  :max="100"
                  :style="{ width: '80px' }"
                />
              </div>
            </div>

            <div class="role-field">
              <label>角色描述</label>
              <ElInput
                v-model="role.agentDescription"
                type="textarea"
                :rows="2"
                size="small"
                placeholder="描述该角色的职责和行为方式"
              />
            </div>

            <div class="role-field">
              <label>可用工具</label>
              <ElCheckboxGroup v-model="role.tools" class="role-tools">
                <ElCheckbox
                  v-for="nt in availableNodeTypes"
                  :key="nt.type"
                  :label="nt.type"
                  :value="nt.type"
                >
                  {{ nt.name }}
                </ElCheckbox>
              </ElCheckboxGroup>
              <div v-if="availableNodeTypes.length === 0" class="role-tools-empty">
                暂无可用工具（节点未注册）
              </div>
            </div>
          </div>
        </div>

        <div v-if="form.roles.length === 0" class="roles-empty">
          尚未添加角色，点击上方"添加角色"按钮
        </div>
      </div>
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
.roles-section {
  margin-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 16px;
}

.roles-section__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.roles-section__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.role-card {
  margin-bottom: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}

.role-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.role-card__index {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}

.role-card__body {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.role-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.role-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.role-field label {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}

.role-field--name {
  flex: 1;
}

.role-field--model {
  width: 180px;
}

.role-field--iters {
  width: 100px;
}

.role-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.role-tools-empty {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  padding: 4px 0;
}

.roles-empty {
  text-align: center;
  padding: 24px;
  color: var(--el-text-color-placeholder);
  font-size: 13px;
}
</style>
