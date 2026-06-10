<script lang="ts" setup>
import { ref, reactive, watch } from 'vue';
import {
  ElDialog, ElForm, ElFormItem, ElInput, ElButton, ElMessage,
  ElCollapse, ElCollapseItem, ElCheckbox, ElCheckboxGroup,
  ElTabPane, ElTabs, ElScrollbar, ElSwitch,
} from 'element-plus';
import {
  updateKnowledgeBaseApi,
  getKbPermissionsApi,
  getRolesApi,
  getDepartmentsApi,
  getUsersApi,
} from '#/api/core/rag';
import type { KnowledgeBase } from '#/api/core/rag';

const emit = defineEmits<{
  saved: [];
}>();

const visible = ref(false);
const saving = ref(false);
const currentKb = ref<KnowledgeBase | null>(null);
const formData = reactive({ name: '', description: '' });

// ─── 共享设置 ───
const activeTab = ref('role');
const expanded = ref<string[]>([]);
const permissionsLoaded = ref(false);

const isPublic = ref(false);
const allRoles = ref<{ id: string; name: string }[]>([]);
const selectedRoleIds = ref<string[]>([]);
const allDepts = ref<{ id: string; name: string }[]>([]);
const selectedDeptIds = ref<string[]>([]);
const allUsers = ref<{ id: string; name: string; username: string }[]>([]);
const selectedUserIds = ref<string[]>([]);
const userSearchKeyword = ref('');

async function loadRoles() {
  try { allRoles.value = await getRolesApi(); }
  catch { console.warn('[description-editor] 加载角色列表失败'); }
}
async function loadDepts() {
  try { allDepts.value = await getDepartmentsApi(); }
  catch { console.warn('[description-editor] 加载部门列表失败'); }
}
async function loadUsers(name?: string) {
  try { allUsers.value = await getUsersApi(name); }
  catch { console.warn('[description-editor] 加载用户列表失败'); }
}
async function loadCurrentPermissions(kbId: string) {
  try {
    const res = await getKbPermissionsApi(kbId);
    isPublic.value = res.is_public;
    selectedRoleIds.value = res.role_ids || [];
    selectedDeptIds.value = res.dept_ids || [];
    selectedUserIds.value = res.user_ids || [];
    permissionsLoaded.value = true;
  } catch {
    permissionsLoaded.value = false;
    ElMessage.warning('加载权限配置失败');
  }
}

watch(userSearchKeyword, (val) => { loadUsers(val || undefined); });

watch(visible, async (val) => {
  if (!val || !currentKb.value) return;
  await loadCurrentPermissions(currentKb.value.id);
  await Promise.all([loadRoles(), loadDepts()]);
  loadUsers();
});

function open(kb: KnowledgeBase) {
  currentKb.value = kb;
  formData.name = kb.name;
  formData.description = kb.description || '';
  isPublic.value = false;
  selectedRoleIds.value = [];
  selectedDeptIds.value = [];
  selectedUserIds.value = [];
  visible.value = true;
}

async function handleSave() {
  if (!currentKb.value) return;
  if (!formData.name.trim()) {
    ElMessage.warning('请输入知识库名称');
    return;
  }
  saving.value = true;
  try {
    const payload: any = {
      name: formData.name.trim(),
      description: formData.description.trim() || undefined,
      is_public: isPublic.value,
    };
    if (permissionsLoaded.value) {
      payload.permissions = {
        role_ids: selectedRoleIds.value,
        dept_ids: selectedDeptIds.value,
        user_ids: selectedUserIds.value,
      };
    }
    await updateKnowledgeBaseApi(currentKb.value.id, payload);
    ElMessage.success('保存成功');
    visible.value = false;
    emit('saved');
  } catch {
    // error handled by request client
  } finally {
    saving.value = false;
  }
}

defineExpose({ open });
</script>

<template>
  <ElDialog
    v-model="visible"
    title="编辑知识库"
    width="600px"
    :close-on-click-modal="false"
  >
    <ElForm label-position="top">
      <ElFormItem label="名称">
        <ElInput v-model="formData.name" />
      </ElFormItem>
      <ElFormItem label="描述">
        <ElInput
          v-model="formData.description"
          type="textarea"
          :rows="4"
          placeholder="请输入知识库描述"
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
      <ElButton type="primary" :loading="saving" @click="handleSave">确定</ElButton>
    </template>
  </ElDialog>
</template>
