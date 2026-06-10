<script lang="ts" setup>
import { ref, reactive, watch } from 'vue';
import {
  ElDialog, ElForm, ElFormItem, ElInput, ElButton, ElMessage,
  ElCollapse, ElCollapseItem, ElCheckbox, ElCheckboxGroup,
  ElTabPane, ElTabs, ElScrollbar, ElSwitch,
} from 'element-plus';
import type { KnowledgeBase } from '#/api/core/rag';
import {
  getKbPermissionsApi,
  getDepartmentsApi,
  getUsersApi,
  getRolesApi,
} from '#/api/core/rag';

const emit = defineEmits<{
  save: [data: {
    name: string;
    description?: string;
    permissions?: {
      role_ids: string[];
      dept_ids: string[];
      user_ids: string[];
    };
  }, editId?: string];
}>();

const visible = ref(false);
const editId = ref<string | undefined>();
const formData = reactive({
  name: '',
  description: '',
});

// ─── 共享设置数据 ───
const activeTab = ref('role');
const expanded = ref<string[]>([]);

// 角色
const allRoles = ref<{ id: string; name: string }[]>([]);
const selectedRoleIds = ref<string[]>([]);
// 权限是否已从后端成功加载（防止未加载时清空权限）
const permissionsLoaded = ref(false);

// 部门
const allDepts = ref<{ id: string; name: string }[]>([]);
const selectedDeptIds = ref<string[]>([]);

// 全员可见开关
const isPublic = ref(false);

// 用户
const allUsers = ref<{ id: string; name: string; username: string }[]>([]);
const selectedUserIds = ref<string[]>([]);
const userSearchKeyword = ref('');

async function loadRoles() {
  try {
    const res = await getRolesApi();
    allRoles.value = res;
  } catch {
    console.warn('[kb-form-dialog] 加载角色列表失败');
  }
}

async function loadDepts() {
  try {
    const res = await getDepartmentsApi();
    allDepts.value = res;
  } catch {
    console.warn('[kb-form-dialog] 加载部门列表失败');
  }
}

async function loadUsers(name?: string) {
  try {
    const res = await getUsersApi(name);
    allUsers.value = res;
  } catch {
    console.warn('[kb-form-dialog] 加载用户列表失败');
  }
}

async function loadCurrentPermissions(kbId: string) {
  try {
    const res = await getKbPermissionsApi(kbId);
    selectedRoleIds.value = res.role_ids || [];
    selectedDeptIds.value = res.dept_ids || [];
    selectedUserIds.value = res.user_ids || [];
    isPublic.value = res.is_public;
    permissionsLoaded.value = true;
  } catch {
    permissionsLoaded.value = false;
    ElMessage.warning('加载权限配置失败，保存时将不会修改现有权限');
  }
}

watch(userSearchKeyword, (val) => {
  loadUsers(val || undefined);
});

watch(visible, async (val) => {
  if (!val) return;
  if (editId.value) {
    await loadCurrentPermissions(editId.value);
  } else {
    selectedRoleIds.value = [];
    selectedDeptIds.value = [];
    selectedUserIds.value = [];
    isPublic.value = false;
    permissionsLoaded.value = true;
  }
  await Promise.all([loadRoles(), loadDepts()]);
  loadUsers();
});

function open(row?: KnowledgeBase) {
  if (row) {
    editId.value = row.id;
    formData.name = row.name;
    formData.description = row.description || '';
    isPublic.value = row.is_public;
  } else {
    editId.value = undefined;
    formData.name = '';
    formData.description = '';
    selectedRoleIds.value = [];
    selectedDeptIds.value = [];
    selectedUserIds.value = [];
    isPublic.value = false;
    permissionsLoaded.value = false;
    expanded.value = [];
  }
  visible.value = true;
}

function handleSave() {
  if (!formData.name.trim()) {
    ElMessage.warning('请输入知识库名称');
    return;
  }
  const payload: any = {
    name: formData.name.trim(),
    description: formData.description.trim() || undefined,
    is_public: isPublic.value,
  };
  // 仅在权限成功加载或新建时才发送 permissions，防止误清空
  if (permissionsLoaded.value) {
    payload.permissions = {
      role_ids: selectedRoleIds.value,
      dept_ids: selectedDeptIds.value,
      user_ids: selectedUserIds.value,
    };
  }
  emit('save', payload, editId.value);
  visible.value = false;
}

defineExpose({ open });
</script>

<template>
  <ElDialog
    v-model="visible"
    :title="editId ? '编辑知识库' : '创建知识库'"
    width="600px"
    :close-on-click-modal="false"
  >
    <ElForm label-width="80px">
      <ElFormItem label="名称" required>
        <ElInput
          v-model="formData.name"
          placeholder="例如: 高中数学知识库"
          maxlength="200"
          show-word-limit
        />
      </ElFormItem>
      <ElFormItem label="描述">
        <ElInput
          v-model="formData.description"
          type="textarea"
          :rows="3"
          placeholder="可选: 知识库描述"
          maxlength="500"
          show-word-limit
        />
      </ElFormItem>
      <ElFormItem label="共享设置">
        <ElCollapse v-model="expanded" style="width:100%">
          <ElCollapseItem title="选择可访问该知识库的角色、部门或用户" name="share">
            <div style="margin-bottom:12px;display:flex;align-items:center;gap:8px">
              <ElSwitch v-model="isPublic" />
              <span style="font-size:13px;color:#606266">全员可见（所有登录用户均可访问）</span>
            </div>
            <template v-if="!isPublic">
              <ElTabs v-model="activeTab">
                <ElTabPane label="角色" name="role">
                <ElScrollbar max-height="260px">
                  <ElCheckboxGroup v-model="selectedRoleIds">
                    <div v-for="r in allRoles" :key="r.id" style="padding:4px 0">
                      <ElCheckbox :label="r.id" :value="r.id">{{ r.name }}</ElCheckbox>
                    </div>
                    <div v-if="allRoles.length === 0" style="color:#999;padding:8px">暂无角色</div>
                  </ElCheckboxGroup>
                </ElScrollbar>
              </ElTabPane>
              <ElTabPane label="部门" name="dept">
                <ElScrollbar max-height="260px">
                  <ElCheckboxGroup v-model="selectedDeptIds">
                    <div v-for="d in allDepts" :key="d.id" style="padding:4px 0">
                      <ElCheckbox :label="d.id" :value="d.id">{{ d.name }}</ElCheckbox>
                    </div>
                    <div v-if="allDepts.length === 0" style="color:#999;padding:8px">暂无部门</div>
                  </ElCheckboxGroup>
                </ElScrollbar>
              </ElTabPane>
              <ElTabPane label="用户" name="user">
                <ElInput
                  v-model="userSearchKeyword"
                  placeholder="搜索用户名或姓名..."
                  clearable
                  style="margin-bottom:8px"
                />
                <ElScrollbar max-height="230px">
                  <ElCheckboxGroup v-model="selectedUserIds">
                    <div v-for="u in allUsers" :key="u.id" style="padding:4px 0">
                      <ElCheckbox :label="u.id" :value="u.id">{{ u.name || u.username }} ({{ u.username }})</ElCheckbox>
                    </div>
                    <div v-if="allUsers.length === 0" style="color:#999;padding:8px">暂无用户</div>
                  </ElCheckboxGroup>
                </ElScrollbar>
              </ElTabPane>
            </ElTabs>
            </template>
          </ElCollapseItem>
        </ElCollapse>
      </ElFormItem>
    </ElForm>
    <template #footer>
      <ElButton @click="visible = false">取消</ElButton>
      <ElButton type="primary" @click="handleSave">保存</ElButton>
    </template>
  </ElDialog>
</template>
