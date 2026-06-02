import { ref } from 'vue';
import {
  aiWritingStream,
  aiEditStream,
  aiEditMessageStream,
  createWriterConversationApi,
  getWriterConversationsApi,
  deleteWriterConversationApi,
  updateWriterConversationTitleApi,
  getWriterMessagesApi,
  updateWriterMessageApi,
  getWriterConversationDocumentsApi,
  createWriterDocumentApi,
  deleteWriterDocumentApi,
  updateWriterDocumentApi,
} from '#/api/core/rag';
import type {
  WriterConversation,
  WriterMessage,
  WriterDocument,
} from '#/api/core/rag';
import type { AiMessage } from '#/components/rag/ChatMessageItem.vue';

export interface ConvItem {
  id: string;
  title: string;
  time: Date;
}

export function useAiWriter() {
  const messages = ref<AiMessage[]>([]);
  const streaming = ref(false);
  const conversations = ref<ConvItem[]>([]);
  const currentConvId = ref<string | null>(null);
  const total = ref(0);
  const loading = ref(false);
  const loadingMessages = ref(false);
  const editingMsgId = ref<string | null>(null);
  const documentsByMsgId = ref<Record<string, WriterDocument[]>>({});
  const messagesVersion = ref(0);

  async function fetchConversations(page = 1, pageSize = 50) {
    loading.value = true;
    try {
      const res = await getWriterConversationsApi({ page, pageSize });
      const data = res as any as { items: WriterConversation[]; total: number };
      conversations.value = (data.items || []).map((c: WriterConversation) => ({
        id: c.id,
        title: c.title,
        time: new Date(c.sys_create_datetime),
      }));
      total.value = data.total || 0;
    } finally {
      loading.value = false;
    }
  }

  async function fetchDocuments(convId: string) {
    try {
      const res = await getWriterConversationDocumentsApi(convId);
      const data = res as any as { items: WriterDocument[]; total: number };
      const map: Record<string, WriterDocument[]> = {};
      for (const doc of data.items || []) {
        if (!map[doc.message_id]) map[doc.message_id] = [];
        (map[doc.message_id] as WriterDocument[]).push(doc);
      }
      documentsByMsgId.value = map;
    } catch {
      documentsByMsgId.value = {};
    }
  }

  async function selectConversation(convId: string) {
    currentConvId.value = convId;
    loadingMessages.value = true;
    try {
      const res = await getWriterMessagesApi(convId);
      const data = res as any as { items: WriterMessage[]; total: number };
      messages.value = (data.items || []).map((m: WriterMessage) => ({
        id: m.id,
        role: m.role,
        content: m.content,
      }));
      await fetchDocuments(convId);
      messagesVersion.value++;
    } finally {
      loadingMessages.value = false;
    }
  }

  async function createConversation(title?: string): Promise<string> {
    const res = await createWriterConversationApi({ title });
    const conv = res as any as WriterConversation;
    conversations.value.unshift({
      id: conv.id,
      title: conv.title,
      time: new Date(conv.sys_create_datetime),
    });
    return conv.id;
  }

  async function deleteConversation(convId: string) {
    await deleteWriterConversationApi(convId);
    const idx = conversations.value.findIndex((c) => c.id === convId);
    if (idx !== -1) conversations.value.splice(idx, 1);
    if (currentConvId.value === convId) {
      currentConvId.value = null;
      messages.value = [];
      documentsByMsgId.value = {};
    }
  }

  async function renameConversation(convId: string, title: string) {
    await updateWriterConversationTitleApi(convId, title);
    const found = conversations.value.find((c) => c.id === convId);
    if (found) found.title = title;
  }

  async function createDocumentFromMessage(
    messageId: string,
    content: string,
  ): Promise<WriterDocument> {
    if (!currentConvId.value) throw new Error('No active conversation');
    const title = content.replace(/<[^>]*>/g, '').slice(0, 30) || '未命名文档';
    const res = await createWriterDocumentApi(
      currentConvId.value,
      messageId,
      title,
      content,
    );
    const doc = res as any as WriterDocument;
    (documentsByMsgId.value[messageId] ??= []).push(doc);
    return doc;
  }

  async function removeDocument(docId: string) {
    await deleteWriterDocumentApi(docId);
    for (const msgId of Object.keys(documentsByMsgId.value)) {
      const docs = documentsByMsgId.value[msgId]!;
      const idx = docs.findIndex((d) => d.id === docId);
      if (idx !== -1) {
        docs.splice(idx, 1);
        if (docs.length === 0) {
          delete documentsByMsgId.value[msgId];
        }
        break;
      }
    }
  }

  async function saveDocumentContent(
    docId: string,
    content: string,
    title?: string,
  ) {
    const res = await updateWriterDocumentApi(docId, { content, title });
    const updated = res as any as WriterDocument;
    for (const msgId of Object.keys(documentsByMsgId.value)) {
      const doc = documentsByMsgId.value[msgId]!.find((d) => d.id === docId);
      if (doc) {
        doc.content = updated.content;
        doc.title = updated.title;
        break;
      }
    }
    return updated;
  }

  async function send(question: string) {
    let convId = currentConvId.value;

    if (!convId) {
      convId = await createConversation(question.slice(0, 20) + '...');
      currentConvId.value = convId;
    }

    const userMsg: AiMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: question,
    };
    messages.value.push(userMsg);

    const assistantMsg: AiMessage = {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      streaming: true,
    };
    messages.value.push(assistantMsg);
    const assistantIdx = messages.value.length - 1;
    streaming.value = true;

    const getMsg = () => messages.value[assistantIdx] as AiMessage;

    // build history from previous messages (exclude the two we just pushed)
    const history = messages.value
      .slice(0, -2)
      .map((m) => ({ role: m.role, content: m.content }));

    try {
      await aiWritingStream(question, convId, history, {
        onToken: (token) => {
          getMsg().content += token;
        },
        onDone: (fullText, returnedConvId, messageId) => {
          const msg = getMsg();
          msg.content = fullText || msg.content;
          msg.streaming = false;
          if (messageId) {
            msg.id = messageId;
          }
          if (returnedConvId) {
            currentConvId.value = returnedConvId;
          }
          fetchConversations();
        },
        onError: (err) => {
          const msg = getMsg();
          msg.content = `错误: ${err.message}`;
          msg.streaming = false;
        },
      });
    } catch (err: any) {
      const msg = getMsg();
      msg.content = `请求失败: ${err.message}`;
      msg.streaming = false;
    } finally {
      streaming.value = false;
    }
  }

  async function updateMessage(messageId: string, newContent: string) {
    const cid = currentConvId.value;
    if (!cid) return;
    await updateWriterMessageApi(cid, messageId, newContent);
    const msg = messages.value.find((m) => m.id === messageId);
    if (msg) {
      msg.content = newContent;
    }
    editingMsgId.value = null;
  }

  async function aiEditMessage(
    messageId: string,
    content: string,
    instruction: 'polish' | 'rewrite' | 'custom',
    customPrompt?: string,
  ): Promise<string> {
    const cid = currentConvId.value;
    if (!cid) throw new Error('No active conversation');

    const msg = messages.value.find((m) => m.id === messageId);
    if (!msg) throw new Error('Message not found');

    msg.content = '';
    streaming.value = true;

    return new Promise((resolve, reject) => {
      let fullText = '';
      aiEditMessageStream(
        cid,
        messageId,
        content,
        instruction,
        customPrompt,
        {
          onToken: (token) => {
            fullText += token;
            msg.content = fullText;
          },
          onDone: (result) => {
            msg.content = result || fullText;
            streaming.value = false;
            editingMsgId.value = null;
            resolve(result || fullText);
          },
          onError: (err) => {
            msg.content = content;
            streaming.value = false;
            reject(err);
          },
        },
      ).catch((err) => {
        msg.content = content;
        streaming.value = false;
        reject(err);
      });
    });
  }

  async function editContent(
    content: string,
    instruction: 'polish' | 'rewrite' | 'custom',
    customPrompt?: string,
  ): Promise<string> {
    return new Promise((resolve, reject) => {
      let fullText = '';
      aiEditStream(content, instruction, customPrompt, {
        onToken: (token) => {
          fullText += token;
        },
        onDone: (fullText_) => {
          resolve(fullText_ || fullText);
        },
        onError: (err) => {
          reject(err);
        },
      }).catch(reject);
    });
  }

  function clearMessages() {
    messages.value = [];
    currentConvId.value = null;
    editingMsgId.value = null;
    documentsByMsgId.value = {};
  }

  function formatTime(date: Date): string {
    const now = Date.now();
    const diff = now - date.getTime();
    const minutes = Math.floor(diff / 60_000);
    if (minutes < 1) return '刚刚';
    if (minutes < 60) return `${minutes} 分钟前`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} 小时前`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days} 天前`;
    return `${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()}`;
  }

  function truncateTitle(title: string): string {
    return title.length > 20 ? `${title.slice(0, 20)}...` : title;
  }

  return {
    messages,
    messagesVersion,
    streaming,
    conversations,
    currentConvId,
    total,
    loading,
    loadingMessages,
    editingMsgId,
    documentsByMsgId,
    send,
    editContent,
    updateMessage,
    aiEditMessage,
    clearMessages,
    fetchConversations,
    selectConversation,
    createConversation,
    deleteConversation,
    renameConversation,
    createDocumentFromMessage,
    removeDocument,
    saveDocumentContent,
    formatTime,
    truncateTitle,
  };
}
