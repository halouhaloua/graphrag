/**
 * 提取工作流输出结果中的文本
 */
export function extractResultText(output: any): string {
  if (!output) return '';
  if (typeof output === 'string') {
    try {
      const parsed = JSON.parse(output);
      if (typeof parsed === 'object') output = parsed;
    } catch {
      return output;
    }
  }
  if (typeof output === 'object') {
    const endResult = output['end-1'];
    if (typeof endResult === 'string' && endResult) return endResult;
    let lastStr = '';
    for (const v of Object.values(output)) {
      if (typeof v === 'string' && v) lastStr = v;
    }
    if (lastStr) return lastStr;
  }
  return JSON.stringify(output);
}
