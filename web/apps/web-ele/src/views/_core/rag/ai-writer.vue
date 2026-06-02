<script lang="ts" setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { Page } from '@vben/common-ui';
import { Download, ListTree, PanelLeft, PanelRight, Plus, Trash2, X } from '@vben/icons';
import { ElButton, ElMessage } from 'element-plus';
import { marked } from 'marked';
import AiChatPanel from '#/components/rag/AiChatPanel.vue';
import { RichTextEditor } from '#/components/zq-form/rich-text-editor';
import SelectionTooltip from '#/components/rag/SelectionTooltip.vue';
import { useAiWriter } from '#/composables/useAiWriter';
import { aiEditStream } from '#/api/core/rag';

defineOptions({ name: 'AiWriterPage' });

const {
  messages,
  messagesVersion,
  streaming,
  conversations,
  currentConvId,
  editingMsgId,
  documentsByMsgId,
  loading,
  send,
  updateMessage,
  aiEditMessage,
  clearMessages,
  fetchConversations,
  selectConversation,
  deleteConversation,
  createDocumentFromMessage,
  removeDocument,
  saveDocumentContent,
  formatTime,
  truncateTitle,
} = useAiWriter();

const sidebarCollapsed = ref(false);
const showEditor = ref(false);
const editorContent = ref('');
const currentDocId = ref<string | null>(null);
const showToc = ref(false);
const editing = ref(false);
const tiptapEditor = ref<any>(null);

// --- Auto-save ---
const saveStatus = ref<'idle' | 'unsaved' | 'saving' | 'saved'>('idle');
let autoSaveTimer: ReturnType<typeof setTimeout> | null = null;

function onEditorChange() {
  if (!currentDocId.value) return;
  saveStatus.value = 'unsaved';
  if (autoSaveTimer) clearTimeout(autoSaveTimer);
  autoSaveTimer = setTimeout(doAutoSave, 3000);
}

async function doAutoSave() {
  if (!currentDocId.value || saveStatus.value !== 'unsaved') return;
  saveStatus.value = 'saving';
  try {
    await saveDocumentContent(currentDocId.value, editorContent.value);
    saveStatus.value = 'saved';
  } catch {
    saveStatus.value = 'unsaved';
  }
}

async function manualSave() {
  if (!currentDocId.value) {
    ElMessage.warning('没有打开的文档');
    return;
  }
  if (autoSaveTimer) clearTimeout(autoSaveTimer);
  await doAutoSave();
}

// --- TOC / Heading ---
interface TocItem {
  level: number;
  id: string;
  text: string;
}

function injectHeadingIdsIntoDOM() {
  const editor = tiptapEditor.value;
  if (!editor) return;
  editor.view.dom.querySelectorAll('h1, h2, h3, h4').forEach((el: HTMLElement, i: number) => {
    el.id = `toc-h-${i}`;
  });
}

const tocItems = computed(() => {
  editorContent.value;
  const editor = tiptapEditor.value;
  if (!editor) return [];
  const items: TocItem[] = [];
  let counter = 0;
  editor.state.doc.descendants((node: any) => {
    if (node.type.name === 'heading' && node.attrs.level <= 4) {
      items.push({
        level: node.attrs.level,
        id: `toc-h-${counter++}`,
        text: node.textContent,
      });
    }
  });
  return items;
});

function scrollToHeading(tocId: string) {
  const editor = tiptapEditor.value;
  if (!editor) return;

  const targetIdx = tocItems.value.findIndex((item) => item.id === tocId);
  if (targetIdx === -1) return;

  nextTick(() => {
    const headings = editor.view.dom.querySelectorAll('h1, h2, h3, h4');
    const target = headings[targetIdx] as HTMLElement | undefined;
    if (!target) return;

    target.id = tocId;

    const scrollContainer = target.closest('.editor-content') as HTMLElement;
    if (scrollContainer) {
      const containerRect = scrollContainer.getBoundingClientRect();
      const targetRect = target.getBoundingClientRect();
      const offset = targetRect.top - containerRect.top + scrollContainer.scrollTop - 16;
      scrollContainer.scrollTo({ top: Math.max(0, offset), behavior: 'smooth' });
    } else {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    target.classList.add('toc-highlight');
    setTimeout(() => target.classList.remove('toc-highlight'), 1500);
  });
}

// --- Follow scroll mode ---
const followScroll = ref(false);
const activeTocId = ref<string | null>(null);
let scrollObserver: IntersectionObserver | null = null;

function toggleFollowScroll() {
  followScroll.value = !followScroll.value;
  if (followScroll.value) {
    nextTick(setupScrollObserver);
  } else {
    scrollObserver?.disconnect();
    activeTocId.value = null;
  }
}

function setupScrollObserver() {
  scrollObserver?.disconnect();
  const editor = tiptapEditor.value;
  if (!editor) return;
  const container = editor.view.dom.closest('.editor-content') as HTMLElement;
  if (!container) return;
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          activeTocId.value = (entry.target as HTMLElement).id;
        }
      }
    },
    { root: container, rootMargin: '-60px 0px 80% 0px', threshold: 0 },
  );
  editor.view.dom.querySelectorAll('h1, h2, h3, h4').forEach((h: Element) => observer.observe(h));
  scrollObserver = observer;
}

// --- Watch: inject heading IDs and re-setup observer on content change ---
watch(editorContent, () => {
  nextTick(() => {
    injectHeadingIdsIntoDOM();
    if (followScroll.value) setupScrollObserver();
  });
}, { flush: 'post' });

onBeforeUnmount(() => {
  scrollObserver?.disconnect();
  if (autoSaveTimer) clearTimeout(autoSaveTimer);
});

// --- Word count ---
const wordCount = computed(() => {
  const text = editorContent.value.replace(/<[^>]*>/g, '').replace(/\s+/g, '');
  return text.length;
});

onMounted(() => {
  fetchConversations();
});

function onEditorReady(editor: any) {
  tiptapEditor.value = editor;
  nextTick(injectHeadingIdsIntoDOM);
}

function getSelectedText(): string {
  const editor = tiptapEditor.value;
  if (!editor?.state) return '';
  const { from, to } = editor.state.selection;
  if (from === to) return '';
  return editor.state.doc.textBetween(from, to, '\n');
}

async function replaceSelectionWithAi(
  instruction: 'polish' | 'rewrite' | 'custom',
  customPrompt?: string,
) {
  const editor = tiptapEditor.value;
  if (!editor) {
    ElMessage.warning('编辑器未就绪');
    return;
  }

  const text = getSelectedText();
  if (!text) {
    ElMessage.warning('请先选中要处理的文本');
    return;
  }

  editing.value = true;
  editor.chain().focus().deleteSelection().run();

  try {
    let fullText = '';
    await aiEditStream(text, instruction, customPrompt, {
      onToken: (token) => {
        fullText += token;
        editor.commands.insertContent(token);
      },
      onDone: () => {
        editing.value = false;
        if (fullText) ElMessage.success('处理完成');
      },
      onError: (err) => {
        editing.value = false;
        ElMessage.error(`处理失败: ${err.message}`);
      },
    });
  } catch {
    editing.value = false;
    ElMessage.error('请求失败');
  }
}

function handlePolish() {
  replaceSelectionWithAi('polish');
}

function handleRewrite() {
  replaceSelectionWithAi('rewrite');
}

function handleCustom(prompt: string) {
  replaceSelectionWithAi('custom', prompt);
}

function handleNewConversation() {
  clearMessages();
  showEditor.value = false;
}

async function handleSelectConversation(convId: string) {
  await selectConversation(convId);
}

async function handleDeleteConversation(convId: string) {
  await deleteConversation(convId);
}

async function handleAiEditMessage(
  messageId: string,
  content: string,
  instruction: string,
  customPrompt?: string,
) {
  try {
    await aiEditMessage(
      messageId,
      content,
      instruction as 'polish' | 'rewrite' | 'custom',
      customPrompt,
    );
  } catch (err: any) {
    ElMessage.error(`AI编辑失败: ${err.message}`);
  }
}

function handleEditMessage(messageId: string, newContent: string) {
  updateMessage(messageId, newContent);
}

async function handleConvert(content: string, msgId: string) {
  showEditor.value = true;
  currentDocId.value = null;
  saveStatus.value = 'idle';
  if (autoSaveTimer) clearTimeout(autoSaveTimer);
  let html = marked.parse(content, { breaks: true }) as string;
  editorContent.value = html;

  try {
    await createDocumentFromMessage(msgId, html);
    saveStatus.value = 'saved';
  } catch {
    saveStatus.value = 'idle';
  }
}

async function handleOpenDocument(doc: any) {
  showEditor.value = true;
  editorContent.value = doc.content;
  currentDocId.value = doc.id;
  saveStatus.value = 'saved';
}

async function handleDeleteDocument(docId: string) {
  try {
    await removeDocument(docId);
  } catch {
    ElMessage.error('删除文档失败');
  }
}

function handleCloseEditor() {
  showEditor.value = false;
  currentDocId.value = null;
  if (autoSaveTimer) clearTimeout(autoSaveTimer);
  saveStatus.value = 'idle';
}

function exportToWord() {
  if (!editorContent.value) {
    ElMessage.warning('编辑器内容为空');
    return;
  }
  const html = `<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'><head><meta charset="utf-8"></head><body>${editorContent.value}</body></html>`;
  const blob = new Blob(['\ufeff' + html], { type: 'application/msword' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = '文档.doc';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
</script>

<template>
  <Page auto-content-height>
    <div class="ai-writer-page">
      <div v-if="!sidebarCollapsed" class="sidebar">
        <div class="sidebar-header">
          <h3>对话历史</h3>
          <div class="sidebar-actions">
            <ElButton :icon="Plus" circle size="small" @click="handleNewConversation" />
            <ElButton
              :icon="PanelLeft"
              circle
              size="small"
              @click="sidebarCollapsed = true"
            />
          </div>
        </div>
        <div class="conv-list">
          <div v-if="loading" class="conv-empty">加载中...</div>
          <div
            v-for="conv in conversations"
            v-else
            :key="conv.id"
            class="conv-item"
            :class="{ active: conv.id === currentConvId }"
            @click="handleSelectConversation(conv.id)"
          >
            <div class="conv-title">{{ truncateTitle(conv.title) }}</div>
            <div class="conv-time">{{ formatTime(conv.time) }}</div>
            <ElButton
              link
              type="danger"
              size="small"
              class="conv-delete"
              :icon="Trash2"
              @click.stop="handleDeleteConversation(conv.id)"
            />
          </div>
          <div v-if="!loading && conversations.length === 0" class="conv-empty">
            暂无对话记录
          </div>
        </div>
      </div>

      <div class="main-area" :class="{ split: showEditor }">
        <div class="chat-area" :class="{ collapsed: showEditor }">
          <ElButton
            v-if="sidebarCollapsed"
            class="expand-btn"
            :icon="PanelRight"
            circle
            size="small"
            @click="sidebarCollapsed = false"
          />
          <AiChatPanel
            :messages="messages"
            :messages-version="messagesVersion"
            :streaming="streaming"
            :editing-msg-id="editingMsgId"
            :documents-by-msg-id="documentsByMsgId"
            @send="send"
            @convert="handleConvert"
            @edit-message="handleEditMessage"
            @ai-edit-message="handleAiEditMessage"
            @open-document="handleOpenDocument"
            @delete-document="handleDeleteDocument"
          />
        </div>

        <div v-show="showEditor" class="editor-wrapper">
          <div class="editor-header">
            <span class="editor-title">文档编辑</span>
            <div class="editor-header-actions">
              <span class="save-status" :class="saveStatus">
                <template v-if="saveStatus === 'saving'">
                  <span class="save-spinner"></span> 保存中...
                </template>
                <template v-else-if="saveStatus === 'unsaved'">未保存</template>
                <template v-else-if="saveStatus === 'saved'">已保存</template>
              </span>
              <span class="word-count">字数: {{ wordCount }}</span>
              <ElButton
                size="small"
                :type="saveStatus === 'unsaved' ? 'primary' : 'default'"
                :disabled="!currentDocId"
                :loading="saveStatus === 'saving'"
                @click="manualSave"
              >
                保存
              </ElButton>
              <ElButton
                :icon="Download"
                circle
                size="small"
                @click="exportToWord"
              />
              <ElButton
                :icon="ListTree"
                circle
                size="small"
                :type="showToc ? 'primary' : 'default'"
                @click="showToc = !showToc"
              />
              <ElButton
                :icon="X"
                circle
                size="small"
                @click="handleCloseEditor"
              />
            </div>
          </div>
          <div class="editor-body">
            <div v-if="showToc && tocItems.length > 0" class="toc-panel">
              <div class="toc-header">
                <span class="toc-title">目录</span>
                <ElButton
                  size="small"
                  text
                  :type="followScroll ? 'primary' : 'default'"
                  @click="toggleFollowScroll"
                >
                  跟随
                </ElButton>
              </div>
              <div class="toc-list">
                <div
                  v-for="item in tocItems"
                  :key="item.id"
                  class="toc-item"
                  :class="{
                    'toc-h2': item.level === 2,
                    'toc-h3': item.level === 3,
                    'toc-h4': item.level === 4,
                    'toc-active': followScroll && item.id === activeTocId,
                  }"
                  @click="scrollToHeading(item.id)"
                >
                  {{ item.text }}
                </div>
              </div>
            </div>
            <RichTextEditor
              v-model="editorContent"
              :max-height="99999"
              :show-word-count="false"
              @ready="onEditorReady"
              @change="onEditorChange"
            />
            <SelectionTooltip
              :editor="tiptapEditor"
              :processing="editing"
              @polish="handlePolish"
              @rewrite="handleRewrite"
              @custom="handleCustom"
            />
          </div>
        </div>
      </div>
    </div>
  </Page>
</template>

<style scoped>
.ai-writer-page {
  display: flex;
  align-items: stretch;
  gap: 12px;
  height: 100%;
}

.sidebar {
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  height: 100%;
  width: 240px;
  overflow: hidden;
  background: var(--el-bg-color-overlay);
  border-radius: 8px;
  transition: width 0.25s ease;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.sidebar-actions {
  display: flex;
  gap: 4px;
  align-items: center;
}

.sidebar-header h3 {
  margin: 0;
  font-size: 15px;
}

.conv-list {
  flex: 1;
  padding: 4px 0;
  overflow-y: auto;
}

.conv-item {
  position: relative;
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 8px 14px;
  cursor: pointer;
  border-left: 3px solid transparent;
}

.conv-item:hover {
  background: var(--el-fill-color-lighter);
}

.conv-item.active {
  background: var(--el-color-primary-light-9);
  border-left-color: var(--el-color-primary);
}

.conv-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  white-space: nowrap;
}

.conv-time {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.conv-delete {
  flex-shrink: 0;
  opacity: 0;
}

.conv-item:hover .conv-delete {
  opacity: 1;
}

.conv-empty {
  padding: 24px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  text-align: center;
}

.main-area {
  display: flex;
  flex: 1;
  flex-direction: column;
  height: 100%;
  min-width: 0;
  min-height: 0;
}

.main-area.split {
  flex-direction: row;
  align-items: stretch;
}

.chat-area {
  position: relative;
  flex: 1;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--el-bg-color-overlay);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 16px;
}

.chat-area.collapsed {
  flex: 0 0 35%;
  border-right: none;
  border-radius: 16px 0 0 16px;
}

.editor-wrapper {
  flex: 0 0 65%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color-overlay);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 0 16px 16px 0;
  overflow: clip;
}

.editor-body {
  flex: 1;
  display: flex;
  flex-direction: row;
  min-height: 0;
}

.toc-panel {
  flex: 0 0 180px;
  overflow-y: auto;
  padding: 12px;
  border-right: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-light);
}

.toc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.toc-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.toc-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.toc-item {
  font-size: 13px;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s;
}

.toc-item:hover {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.toc-item.toc-active {
  background: var(--el-color-primary-light-8);
  color: var(--el-color-primary);
  font-weight: 600;
}

.toc-h2 {
  padding-left: 20px;
  font-size: 12px;
}

.toc-h3 {
  padding-left: 32px;
  font-size: 12px;
}

.toc-h4 {
  padding-left: 44px;
  font-size: 11px;
}

.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 14px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.editor-title {
  font-size: 14px;
  font-weight: 500;
}

.editor-header-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

.save-status {
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.save-status.saving {
  color: var(--el-color-warning);
}

.save-status.unsaved {
  color: var(--el-color-danger);
}

.save-status.saved {
  color: var(--el-color-success);
}

.save-spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid var(--el-color-warning);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.word-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.editor-wrapper :deep(.rich-text-editor),
.editor-body :deep(.rich-text-editor) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  border: none;
  border-radius: 0;
}

.editor-wrapper :deep(.editor-content) {
  flex: 1;
  min-height: 0;
  overflow: auto;
  position: relative;
}

.editor-wrapper :deep(.toolbar) {
  position: sticky;
  top: 0;
  z-index: 1;
}

.editor-wrapper :deep(.toolbar .el-button.is-active) {
  border-radius: 4px;
}

.editor-wrapper :deep(.tiptap) {
  max-width: 720px;
  margin: 0 auto;
  line-height: 1.8;
}

.editor-wrapper :deep(.tiptap > * + *) {
  margin-top: 1.2em;
}

.editor-wrapper :deep(.toc-highlight) {
  animation: tocFlash 1.5s ease;
}

@keyframes tocFlash {
  0%, 100% { background: transparent; }
  15%, 35% { background: var(--el-color-warning-light-5); border-radius: 4px; }
}

.expand-btn {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 2;
  box-shadow: 0 6px 16px rgb(15 23 42 / 10%);
}
</style>
