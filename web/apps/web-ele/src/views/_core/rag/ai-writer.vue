<script lang="ts" setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { Page } from '@vben/common-ui';
import { Download, ListTree, PanelLeft, PanelRight, Plus, Trash2, X } from '@vben/icons';
import { ElButton, ElMessage } from 'element-plus';
import { marked } from 'marked';
import AiChatPanel from '#/components/rag/AiChatPanel.vue';
import KbFileSelector from '#/components/rag/KbFileSelector.vue';
import { RichTextEditor } from '#/components/zq-form/rich-text-editor';
import SelectionTooltip from '#/components/rag/SelectionTooltip.vue';
import { useAiWriter } from '#/composables/useAiWriter';
import { aiEditStream, getKnowledgeBaseListApi } from '#/api/core/rag';
import type { KnowledgeBase } from '#/api/core/rag';

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
  kbIds,
  selectedKbLabel,
  setKbIds,
} = useAiWriter();

const sidebarCollapsed = ref(false);
const showEditor = ref(false);
const editorContent = ref('');
const currentDocId = ref<string | null>(null);
const showToc = ref(false);
const editing = ref(false);
const tiptapEditor = ref<any>(null);

// ─── 知识库选择 ───
const showKbSelector = ref(false);
const kbs = ref<KnowledgeBase[]>([]);

async function loadKbs() {
  try {
    const res = await getKnowledgeBaseListApi({ page: 1, pageSize: 200 });
    kbs.value = res.items;
  } catch {
    kbs.value = [];
  }
}

function handleKbSelect(kbId: string, _fileId: string) {
  setKbIds(kbIds.value.includes(kbId) ? kbIds.value : [...kbIds.value, kbId]);
  showKbSelector.value = false;
}

onMounted(() => {
  loadKbs();
});

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

function _buildDemoMessages() {
  const report = [
    '[规划] 篇目规划完成: 共 7 节',
    '[检索] 主题分解: 拆解为 5 个方面（建置沿革、农业经济、工业发展、人口民族、文化教育）',
    '[检索]   建置沿革: 召回 12 条，保留 10 条，移除 2 条',
    '[检索]   农业经济: 召回 18 条，保留 15 条，移除 3 条',
    '[检索]   工业发展: 召回 8 条，保留 8 条',
    '[检索]   人口民族: 召回 6 条，保留 5 条，移除 1 条',
    '[检索]   文化教育: 召回 10 条，保留 8 条，移除 2 条',
    '[验证] 验证 46 条，发现 1 处矛盾',
    '[审校] 相关度终审完成: 保留 44 条，移除 2 条',
    '[撰写] 共撰写 7 节，总计 12600 字',
    '[统稿] 统稿合成完成',
    '[审查] 审查发现 4 个问题',
    '[质检] 质检评分: 0.85',
    '[完成] 志书生成完毕',
  ].join('\n');
  const reportDetails = [
    {
      summary: '[检索] 建置沿革: 移除 2 条',
      details: ['移除: (龙华镇, 气候类型, 亚热带季风) — 与建置沿革主题无关[score: 0.32]', '移除: (龙华镇, 土壤类型, 红壤) — 属于自然环境方面而非建置沿革[score: 0.28]'],
    },
    {
      summary: '[检索] 农业经济: 移除 3 条',
      details: ['移除: (龙华镇, 工业总产值, 5.6亿元) — 属于工业发展方面[score: 0.15]', '移除: (龙华镇, 学校数量, 11所) — 属于文化教育方面[score: 0.20]', '移除: (龙华镇, 人口密度, 153人/km²) — 属于人口民族方面[score: 0.35]'],
    },
    {
      summary: '[验证] 发现 1 处矛盾',
      details: ['矛盾: 农业产值数据不一致 — 本志记载3.2亿元，统计年鉴显示3.15亿元，差异约500万元'],
    },
    {
      summary: '[审查] 发现 4 个问题',
      details: ['[critical] 农业产值数据与2020年统计年鉴不一致', '[major] 龙华镇平均海拔数据缺少来源', '[minor] "社队企业"应改为"乡镇企业"更符合本地用语习惯', '[minor] 文化教育章节缺少"体育事业"内容，建议补充'],
    },
  ];
  const kgData = {
    aspects: [
      {
        name: '建置沿革',
        recall_query: '龙华镇建置沿革历史变迁',
        triples: [
          '(龙华镇, 建镇时间, 1984年) [score: 0.952]',
          '(龙华镇, 前身, 龙华公社) [score: 0.935]',
          '(龙华镇, 所属, 某某县) [score: 0.921]',
          '(龙华镇, 面积, 186.7平方公里) [score: 0.898]',
          '(龙华镇, 地理位置, 某某县东南部) [score: 0.876]',
          '(龙华镇, 东邻, 凤城镇) [score: 0.832]',
          '(龙华镇, 西连, 城关镇) [score: 0.815]',
          '(龙华镇, 平均海拔, 280米) [score: 0.792]',
          '(龙华镇, 气候类型, 亚热带季风气候) [score: 0.768]',
          '(龙华镇, 年均气温, 18.5℃) [score: 0.754]',
        ],
        chunks: ['龙华镇位于某某县东南部，东经118°42′，北纬27°03′。1984年撤销龙华公社，设立龙华镇。2005年全镇面积扩大至186.7平方公里。'],
        triple_count: 10,
        chunk_count: 1,
      },
      {
        name: '农业经济',
        recall_query: '龙华镇农业经济产业结构',
        triples: [
          '(龙华镇, 农业总产值2020, 3.2亿元) [score: 0.945]',
          '(龙华镇, 主要作物, 水稻/茶叶/柑橘) [score: 0.923]',
          '(龙华镇, 粮食播种面积, 1.2万亩) [score: 0.912]',
          '(龙华镇, 粮食总产, 5200吨) [score: 0.887]',
          '(龙华镇, 茶园面积, 3500亩) [score: 0.865]',
          '(龙华镇, 茶叶产量, 280吨) [score: 0.842]',
          '(龙华镇, 茶叶产值, 4200万元) [score: 0.828]',
          '(龙华镇, 森林覆盖率, 68%) [score: 0.815]',
          '(龙华镇, 林业用地, 12.5万亩) [score: 0.793]',
          '(龙华镇, 林业产值, 4800万元) [score: 0.776]',
          '(龙华镇, 生猪出栏, 1.8万头) [score: 0.752]',
          '(龙华镇, 畜牧业产值, 8000万元) [score: 0.734]',
          '(龙华镇, "龙华云雾茶", 省名茶称号) [score: 0.698]',
          '(龙华镇, 种植业占比, 45%) [score: 0.683]',
          '(龙华镇, 渔业占比, 15%) [score: 0.652]',
        ],
        chunks: [
          '龙华镇是某某县重要的农业产区。2020年全镇农业总产值3.2亿元，其中种植业占45%，林业占15%，畜牧业占25%，渔业占15%。',
          '主要农产品有水稻、茶叶、水果（柑橘、杨梅）、竹笋等。茶叶是龙华镇特色产业，2020年茶园面积3500亩，产量280吨，产值4200万元。"龙华云雾茶"获省名茶称号。',
        ],
        triple_count: 15,
        chunk_count: 2,
      },
      {
        name: '工业发展',
        recall_query: '龙华镇工业发展企业情况',
        triples: [
          '(龙华镇, 工业总产值2020, 5.6亿元) [score: 0.938]',
          '(龙华镇, 规上企业数, 12家) [score: 0.915]',
          '(龙华镇, 主要行业, 食品加工/竹木家具/茶叶精制) [score: 0.892]',
          '(龙华竹业, 创建时间, 1992年) [score: 0.875]',
          '(龙华竹业, 年产竹地板, 50万平方米) [score: 0.856]',
          '(龙华竹业, 2020年产值, 1.2亿元) [score: 0.832]',
          '(龙华茶业, 级别, 省级农业龙头企业) [score: 0.815]',
          '(龙华茶业, 年产精制茶, 100吨) [score: 0.793]',
        ],
        chunks: ['龙华镇工业以农产品加工和竹木制品为主。2020年全镇工业总产值5.6亿元。规模以上企业12家。20世纪90年代，乡镇企业发展迅速，形成以竹制品、茶叶加工为主导的工业体系。'],
        triple_count: 8,
        chunk_count: 1,
      },
      {
        name: '人口民族',
        recall_query: '龙华镇人口民族构成变化',
        triples: [
          '(龙华镇, 总人口2020, 2.86万人) [score: 0.945]',
          '(龙华镇, 男性人口, 1.48万人) [score: 0.923]',
          '(龙华镇, 女性人口, 1.38万人) [score: 0.912]',
          '(龙华镇, 汉族占比, 99.2%) [score: 0.895]',
          '(龙华镇, 少数民族占比, 0.8%) [score: 0.876]',
        ],
        chunks: ['2020年第七次全国人口普查，龙华镇总人口2.86万人。其中男性1.48万人，女性1.38万人。全镇以汉族为主，占总人口的99.2%。少数民族有畲族、回族等，共0.8%。'],
        triple_count: 5,
        chunk_count: 1,
      },
      {
        name: '文化教育',
        recall_query: '龙华镇文化教育事业发展',
        triples: [
          '(龙华镇, 初级中学, 1所) [score: 0.938]',
          '(龙华镇, 小学, 4所) [score: 0.925]',
          '(龙华镇, 幼儿园, 6所) [score: 0.912]',
          '(龙华镇, 在校学生, 3200人) [score: 0.898]',
          '(龙华镇, 教职工, 210人) [score: 0.875]',
          '(龙华镇, 文化站, 1个) [score: 0.852]',
          '(龙华镇, 农家书屋, 12个) [score: 0.838]',
        ],
        chunks: ['龙华镇有初级中学1所，小学4所，幼儿园6所。2020年在校学生3200人，教职工210人。镇文化站1个，农家书屋12个。非物质文化遗产有龙华竹编、龙华山歌。'],
        triple_count: 7,
        chunk_count: 1,
      },
    ],
    removed_items: [
      { content: '(龙华镇, 气候类型, 亚热带季风) [score: 0.768]', reason: '与建置沿革主题无关，属于自然环境方面' },
      { content: '(龙华镇, 土壤类型, 红壤) [score: 0.701]', reason: '属于自然环境方面而非建置沿革' },
      { content: '(龙华镇, 工业总产值2020, 5.6亿元) [score: 0.938]', reason: '属于工业发展方面，非农业经济' },
      { content: '(龙华镇, 学校数量, 11所) [score: 0.687]', reason: '属于文化教育方面，非农业经济' },
      { content: '(龙华镇, 人口密度, 153人/km²) [score: 0.624]', reason: '属于人口民族方面，非农业经济' },
      { content: '(龙华镇, 工业用地面积, 1200亩) [score: 0.592]', reason: '属于工业发展方面，非建置沿革' },
      { content: '(龙华镇, 年降水量, 1650mm) [score: 0.568]', reason: '属于自然环境方面，非建置沿革' },
      { content: '(龙华镇, 户籍人口, 2.75万人) [score: 0.556]', reason: '与常住人口数据重复，非文化教育' },
    ],
  };
  const content = [
    '<h2>凡例</h2>',
    '<p>一、本志以马克思主义为指导，全面记述龙华镇自然、经济、政治、文化、社会的历史与现状。</p>',
    '<p>二、本志断限为1980年至2025年。</p>',
    '<h2>第一章 建置沿革</h2>',
    '<p>龙华镇位于某某县东南部。1984年设立龙华镇。2005年全镇面积扩大至186.7平方公里。</p>',
    '<h2>第二章 农业经济</h2>',
    '<p>龙华镇是某某县重要的农业产区。2020年全镇农业总产值3.2亿元。主要农产品有水稻、茶叶、柑橘等。</p>',
    '<h2>第三章 工业发展</h2>',
    '<p>2020年全镇工业总产值5.6亿元。规模以上企业12家。以农产品加工和竹木制品为主。</p>',
    '<h2>第四章 人口民族</h2>',
    '<p>2020年龙华镇总人口2.86万人。全镇以汉族为主，少数民族占0.8%。</p>',
    '<h2>第五章 文化教育</h2>',
    '<p>龙华镇有初级中学1所，小学4所，幼儿园6所。2020年在校学生3200人。</p>',
    '<h2>第六章 社会事业</h2>',
    '<p>龙华镇卫生院1所。2020年全镇农民人均可支配收入2.15万元。</p>',
  ].join('\n');

  return { content, report, reportDetails, kgData };
}

function handleLoadDemo() {
  clearMessages();
  const demoConvId = 'demo_conv_' + Date.now();
  conversations.value.unshift({
    id: demoConvId,
    title: '某某县龙华镇志（演示）',
    time: new Date(),
  } as any);
  currentConvId.value = demoConvId;
  _restoreDemoMessages();
}

function _restoreDemoMessages() {
  const demo = _buildDemoMessages();
  messages.value = [
    {
      id: 'user-demo-1',
      role: 'user',
      content: '帮我写一篇关于某某县经济变迁的镇志',
      streaming: false,
    },
    {
      id: 'assistant-demo-1',
      role: 'assistant',
      content: demo.content,
      report: demo.report,
      report_details: demo.reportDetails,
      kg_data: demo.kgData,
      streaming: false,
    } as any,
  ];
}

async function handleSelectConversation(convId: string) {
  if (convId.startsWith('demo_conv_')) {
    const found = conversations.value.find((c) => c.id === convId);
    if (!found) return;
    currentConvId.value = convId;
    showEditor.value = false;
    _restoreDemoMessages();
    return;
  }
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
        <div class="sidebar-footer">
          <el-button
            size="small"
            class="demo-btn"
            @click="handleLoadDemo"
          >
            加载演示数据
          </el-button>
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
            :kb-ids="kbIds"
            :selected-kb-label="selectedKbLabel"
            @send="send"
            @convert="handleConvert"
            @edit-message="handleEditMessage"
            @ai-edit-message="handleAiEditMessage"
            @open-document="handleOpenDocument"
            @delete-document="handleDeleteDocument"
            @open-kb-selector="showKbSelector = true"
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
    <KbFileSelector
      v-model="showKbSelector"
      :kbs="kbs"
      :selected-kb-id="kbIds[0] || ''"
      :selected-file-id="''"
      @select="handleKbSelect"
    />
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

.sidebar-footer {
  padding: 8px 14px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.demo-btn {
  width: 100%;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-color: transparent;
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
