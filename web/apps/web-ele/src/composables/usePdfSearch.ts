import { ref, shallowRef, onUnmounted } from 'vue';
import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import type { TextItem } from 'pdfjs-dist/types/src/display/api';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

// 配置 Worker
GlobalWorkerOptions.workerSrc = workerUrl;

export interface PdfMatch {
  pageNum: number;
  text: string;
  before: string;
  after: string;
}

export function usePdfSearch() {
  // 核心修复：使用 shallowRef 避免 Vue 深度代理破坏 pdfjs 内部的 JS 私有字段
  const pdfDoc = shallowRef<PDFDocumentProxy | null>(null);
  const loading = ref(false);
  const error = ref('');
  const allText = ref<string[]>([]);
  const matches = ref<PdfMatch[]>([]);
  const matchIndex = ref(-1); // -1 表示无匹配或未开始
  const totalMatches = ref(0);

  let loadToken = 0; // 用于处理竞态条件

  /**
   * 安全销毁 PDF 文档，释放内存
   */
  function destroyPdf() {
    if (pdfDoc.value) {
      try {
        (pdfDoc.value as any).destroy();
      } catch {
        // pdfjs-dist 新版本可能没有 destroy 方法
      }
      pdfDoc.value = null;
    }
  }

  /**
   * 加载 PDF 文档并提取纯文本
   */
  async function loadPdf(url: string) {
    const token = ++loadToken;
    loading.value = true;
    error.value = '';
    matches.value = [];
    totalMatches.value = 0;
    matchIndex.value = -1;
    allText.value = [];

    // 加载新文档前，安全销毁旧文档
    destroyPdf();

    try {
      // 核心优化：传入 verbosity: 0 (ERRORS)，屏蔽 "TT: undefined function" 等无害警告
      const doc = await getDocument({ url, verbosity: 0 }).promise;
      
      // 检查是否被新的请求覆盖（竞态处理）
      if (token !== loadToken) {
        try {
          (doc as any).destroy();
        } catch {
          // pdfjs-dist 新版本可能没有 destroy 方法
        }
        return;
      }
      
      pdfDoc.value = doc;

      const texts: string[] = [];
      for (let i = 1; i <= doc.numPages; i++) {
        // 在长循环中再次检查，支持中途取消
        if (token !== loadToken) return;

        const page = await doc.getPage(i);
        const content = await page.getTextContent();
        
        // 核心修复：过滤掉 TextMarkedContent，只保留 TextItem，避免 undefined 产生多余空格
        const text = content.items
          .filter((item): item is TextItem => 'str' in item)
          .map((item) => item.str)
          .join(' ');
          
        texts.push(text);
      }
      
      if (token !== loadToken) return;

      // 核心优化：一次性赋值，避免循环中频繁触发 Vue 的响应式更新
      allText.value = texts;
    } catch (e: unknown) {
      if (token !== loadToken) return;
      const msg = e instanceof Error ? e.message : String(e);
      console.error('[usePdfSearch] loadPdf failed:', msg);
      error.value = msg;
    } finally {
      if (token === loadToken) {
        loading.value = false;
      }
    }
  }

  /**
   * 在已加载的文本中搜索关键字
   */
  function search(query: string) {
    matches.value = [];
    matchIndex.value = -1;
    totalMatches.value = 0;

    if (!query || !allText.value.length) return;

    const q = query.toLowerCase();
    const results: PdfMatch[] = [];

    for (let pageIdx = 0; pageIdx < allText.value.length; pageIdx++) {
      const text = allText.value[pageIdx];
      const lower = text.toLowerCase();
      let pos = 0;
      
      while (true) {
        const idx = lower.indexOf(q, pos);
        if (idx === -1) break;

        const start = Math.max(0, idx - 30);
        const end = Math.min(text.length, idx + query.length + 30);
        
        const before = (idx > 30 ? '...' : '') + text.slice(start, idx);
        const after = text.slice(idx + query.length, end) + (end < text.length ? '...' : '');

        results.push({
          pageNum: pageIdx + 1,
          text: text.slice(idx, idx + query.length),
          before,
          after,
        });
        
        pos = idx + 1;
      }
    }

    matches.value = results;
    totalMatches.value = results.length;
    
    // 如果有结果，默认选中第一个
    if (results.length > 0) {
      matchIndex.value = 0;
    }
  }

  /**
   * 跳转到指定索引的匹配项
   */
  function goToMatch(index: number) {
    if (index < 0 || index >= matches.value.length) return null;
    matchIndex.value = index;
    return matches.value[index].pageNum;
  }

  /**
   * 下一个匹配项（线性跳转，配合 UI 的 disabled 逻辑）
   */
  function nextMatch() {
    if (matchIndex.value < matches.value.length - 1) {
      return goToMatch(matchIndex.value + 1);
    }
    return null;
  }

  /**
   * 上一个匹配项（线性跳转，配合 UI 的 disabled 逻辑）
   */
  function prevMatch() {
    if (matchIndex.value > 0) {
      return goToMatch(matchIndex.value - 1);
    }
    return null;
  }

  // 组件卸载时自动清理资源，防止内存泄漏
  onUnmounted(() => {
    destroyPdf();
  });

  return {
    loading,
    error,
    allText,
    matches,
    matchIndex,
    totalMatches,
    loadPdf,
    search,
    goToMatch,
    nextMatch,
    prevMatch,
    destroyPdf,
  };
}