import { requestClient } from '#/api/request';

export namespace RagFileApi {
  export interface FileItem {
    id?: string;
    name: string;
    fileType: 'file' | 'folder';
    fileSize?: number;
    fileExt?: string;
    parentId?: string;
    path?: string;
    storagePath?: string;
    mimeType?: string;
    md5?: string;
    scope?: string;
    hasChildren?: boolean;
    updatedTime?: string;
    /** 兼容后端返回的 snake_case 字段 */
    file_type?: string;
    type?: string;
    size?: number;
    kbId?: string;
  }

  export interface FileListParams {
    parentId?: null | string;
    scope?: string;
    fileType?: 'file' | 'folder';
    page?: number;
    pageSize?: number;
    creatorId?: string;
  }

  export interface FileListResult {
    items: FileItem[];
    total: number;
  }

  export interface FolderCreateParams {
    name: string;
    parentId?: string;
    scope?: string;
  }
}

async function getFileList(params?: RagFileApi.FileListParams) {
  return requestClient.get<RagFileApi.FileListResult>(
    '/rag/api/file-manager',
    { params },
  );
}

async function uploadFile(
  file: File,
  scope: string = 'personal',
  parentId?: string,
  onProgress?: (progressEvent: {
    loaded: number;
    percentage: number;
    total: number;
  }) => void,
) {
  return requestClient.upload(
    '/rag/api/file-manager/upload',
    {
      file,
      parentId: parentId || undefined,
      scope,
    },
    {
      onUploadProgress: (progressEvent: any) => {
        if (onProgress && progressEvent.total) {
          const percentage = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total,
          );
          onProgress({
            loaded: progressEvent.loaded,
            total: progressEvent.total,
            percentage,
          });
        }
      },
    },
  );
}

async function createFolder(data: RagFileApi.FolderCreateParams) {
  return requestClient.post('/rag/api/file-manager/folder', data);
}

async function getFolderTree(scope?: string) {
  return requestClient.get<Array<any>>('/rag/api/file-manager/tree', {
    params: scope ? { scope } : undefined,
  });
}

async function renameItem(id: string, data: { name: string }) {
  return requestClient.put(`/rag/api/file-manager/${id}/rename`, data);
}

async function deleteItem(id: string) {
  return requestClient.delete(`/rag/api/file-manager/${id}`);
}

async function batchDelete(data: { ids: string[] }) {
  return requestClient.post('/rag/api/file-manager/batch/delete', data);
}

function getFileStreamUrl(fileId: string, token: string): string {
  return `/basic-api/rag/api/file-manager/stream/${fileId}?token=${token}`;
}

function getDownloadUrl(path: string, token: string): string {
  return `/basic-api/rag/api/file-manager/download?path=${encodeURIComponent(path)}&token=${token}`;
}

async function getRagFileInfo(fileId: string) {
  return requestClient.get<{
    id: string;
    name: string;
    fileType: string;
    fileExt?: string;
    mimeType?: string;
  }>(`/rag/api/file-manager/file-info/${fileId}`);
}

async function getFileText(fileId: string) {
  return requestClient.get<{
    textContent?: string;
    ocrStatus: string;
    llmStatus: string;
  }>(`/rag/api/file-manager/${fileId}/text`);
}

async function updateFileText(fileId: string, textContent: string) {
  return requestClient.put(`/rag/api/file-manager/${fileId}/text`, {
    textContent,
  });
}

async function addFileToKb(fileId: string, kbId: string) {
  return requestClient.post(`/rag/api/file-manager/${fileId}/add-to-kb`, {
    kbId,
  });
}

async function triggerOcr(fileId: string) {
  return requestClient.post(`/rag/api/file-manager/${fileId}/ocr`);
}

async function triggerComplexOcr(fileId: string) {
  return requestClient.post(`/rag/api/file-manager/${fileId}/complex-ocr`);
}

async function getKbListForSelect(page = 1, pageSize = 200) {
  return requestClient.get<{ items: Array<{ id: string; name: string; description?: string }>; total: number }>(
    '/rag/api/knowledge-bases',
    { params: { page, pageSize } },
  );
}

// ─── KB File APIs ───

async function getKbFileTree() {
  return requestClient.get<Array<{ id: string; name: string; fileType: string; hasChildren: boolean }>>(
    '/rag/api/knowledge-base/files/tree',
  );
}

async function getKbFileList(kbId: string) {
  return requestClient.get<{ items: Array<{
    id: string;
    filename: string;
    fileType?: string;
    fileSize?: number;
    hasGraph?: boolean;
    kbId: string;
    kbName?: string;
  }>; total: number }>(
    `/rag/api/knowledge-base/${kbId}/files`,
  );
}

async function getKbFileText(fileId: string) {
  return requestClient.get<{
    textContent: string;
    filename: string;
    fileExt: string;
    kbId: string;
    kbName: string;
  }>(`/rag/api/knowledge-base/files/${fileId}/text`);
}

async function updateKbFileText(fileId: string, textContent: string) {
  return requestClient.put(`/rag/api/knowledge-base/files/${fileId}/text`, { textContent });
}

function getKbFileStreamUrl(fileId: string, kbId: string, token: string): string {
  return `/basic-api/rag/api/knowledge-base/${kbId}/files/${fileId}/preview?token=${token}`;
}

export {
  addFileToKb,
  batchDelete,
  createFolder,
  deleteItem,
  getDownloadUrl,
  getFileList,
  getFileStreamUrl,
  getFileText,
  getFolderTree,
  getKbFileList,
  getKbFileStreamUrl,
  getKbFileText,
  getKbFileTree,
  getKbListForSelect,
  getRagFileInfo,
  renameItem,
  triggerComplexOcr,
  triggerOcr,
  updateFileText,
  updateKbFileText,
  uploadFile,
};
