export interface NodeTypeMeta {
  type: string;
  label: string;
  icon: string;
  color: string;
  category: 'trigger' | 'ai' | 'tool' | 'code' | 'flow';
  description: string;
  inputs: number;
  outputs: number;
  defaultParams: Record<string, any>;
}

export const NODE_TYPE_MAP: Record<string, NodeTypeMeta> = {
  _start: {
    type: '_start',
    label: '开始',
    icon: 'circle-play',
    color: '#22c55e',
    category: 'flow',
    description: '工作流起点',
    inputs: 0,
    outputs: 1,
    defaultParams: {},
  },
  _end: {
    type: '_end',
    label: '结束',
    icon: 'circle-check-big',
    color: '#64748b',
    category: 'flow',
    description: '工作流终点',
    inputs: 1,
    outputs: 0,
    defaultParams: {},
  },
  chat: {
    type: 'chat',
    label: 'LLM对话',
    icon: 'message-square-more',
    color: '#3b82f6',
    category: 'ai',
    description: '调用大语言模型进行对话',
    inputs: 1,
    outputs: 1,
    defaultParams: { temperature: 0.7, system_prompt: '' },
  },
  serper_search: {
    type: 'serper_search',
    label: 'Serper搜索',
    icon: 'search',
    color: '#f97316',
    category: 'tool',
    description: '通过Serper API搜索最新信息',
    inputs: 1,
    outputs: 1,
    defaultParams: { query: '', max_results: 10 },
  },
  web_crawler: {
    type: 'web_crawler',
    label: '网络爬虫',
    icon: 'globe',
    color: '#f59e0b',
    category: 'tool',
    description: '爬取网页正文内容',
    inputs: 1,
    outputs: 1,
    defaultParams: { url: '' },
  },
  api_call: {
    type: 'api_call',
    label: 'API调用',
    icon: 'link',
    color: '#a855f7',
    category: 'tool',
    description: '通用REST API调用',
    inputs: 1,
    outputs: 1,
    defaultParams: { url: '', method: 'GET' },
  },
  python_execute: {
    type: 'python_execute',
    label: '代码执行',
    icon: 'terminal',
    color: '#ef4444',
    category: 'code',
    description: '在沙箱中执行Python/Shell代码',
    inputs: 1,
    outputs: 1,
    defaultParams: { language: 'python', code: '' },
  },
  browser_agent: {
    type: 'browser_agent',
    label: '浏览器自动化',
    icon: 'monitor',
    color: '#14b8a6',
    category: 'tool',
    description: '使用浏览器自动执行网页操作',
    inputs: 1,
    outputs: 1,
    defaultParams: { task: '' },
  },
  arxiv_search: {
    type: 'arxiv_search',
    label: 'Arxiv论文',
    icon: 'library',
    color: '#6366f1',
    category: 'tool',
    description: '搜索Arxiv学术论文库',
    inputs: 1,
    outputs: 1,
    defaultParams: { query: '', max_results: 5 },
  },
  weather_forecast: {
    type: 'weather_forecast',
    label: '天气预报',
    icon: 'cloud-sun',
    color: '#06b6d4',
    category: 'tool',
    description: '通过彩云天气API获取天气信息',
    inputs: 1,
    outputs: 1,
    defaultParams: { latitude: 0, longitude: 0 },
  },
};

export const NODE_CATEGORIES = [
  { key: 'flow', label: '流程控制' },
  { key: 'ai', label: 'AI 能力' },
  { key: 'tool', label: '工具' },
  { key: 'code', label: '代码执行' },
] as const;

export function getNodeMeta(type: string): NodeTypeMeta | null {
  return NODE_TYPE_MAP[type] || null;
}

export function truncateText(text: string, maxLen: number): string {
  if (!text) return '';
  return text.length > maxLen ? text.slice(0, maxLen) + '...' : text;
}
