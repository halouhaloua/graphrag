<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import { getFileStreamUrl, getFileStream } from '#/api/core/file';
import VueOfficePdf from '@vue-office/pdf';
import VueOfficeDocx from '@vue-office/docx';

const props = withDefaults(defineProps<{
  fileId: string;
  fileName?: string;
  fileExt?: string;
  customPreviewUrl?: string;
  customFetchBlob?: () => Promise<Blob>;
  zoom?: number;
}>(), {
  fileName: '',
  fileExt: '',
  zoom: 1,
});

const loading = ref(false);
const error = ref('');
const previewUrl = ref('');
const textContent = ref('');

const pdfRef = ref<any>(null);

function applyZoom() {
  const z = props.zoom ?? 1;
  if (previewType.value === 'pdf' && pdfRef.value?.setScale) {
    pdfRef.value.setScale(z);
  }
}

watch(() => props.zoom, applyZoom);

type PreviewType = 'pdf' | 'docx' | 'text' | 'image' | 'video' | 'audio' | 'unsupported';
const previewType = ref<PreviewType>('unsupported');

const fileTypeMap: Record<string, PreviewType> = {
  pdf: 'pdf',
  docx: 'docx',
  txt: 'text', md: 'text', json: 'text', xml: 'text',
  yaml: 'text', yml: 'text', csv: 'text', log: 'text',
  ini: 'text', cfg: 'text', py: 'text', js: 'text',
  ts: 'text', jsx: 'text', tsx: 'text', html: 'text',
  css: 'text', scss: 'text', less: 'text', java: 'text',
  cpp: 'text', c: 'text', h: 'text', sql: 'text',
  sh: 'text', bat: 'text', ps1: 'text', env: 'text',
  gitignore: 'text', dockerfile: 'text',
  png: 'image', jpg: 'image', jpeg: 'image', gif: 'image',
  svg: 'image', bmp: 'image', webp: 'image', ico: 'image',
  mp4: 'video', webm: 'video', ogg: 'video', mov: 'video',
  avi: 'video', mkv: 'video',
  mp3: 'audio', wav: 'audio', flac: 'audio', aac: 'audio',
};

function getExt() {
  return (props.fileExt || '').toLowerCase().replace(/^\./, '');
}

function resolvePreviewType(): PreviewType {
  const ext = getExt();
  return fileTypeMap[ext] || 'unsupported';
}

async function loadPreview() {
  loading.value = true;
  error.value = '';
  previewType.value = resolvePreviewType();

  try {
    switch (previewType.value) {
      case 'pdf':
      case 'docx':
      case 'image':
      case 'video':
      case 'audio':
        previewUrl.value = props.customPreviewUrl || getFileStreamUrl(props.fileId);
        break;
      case 'text': {
        const blob = props.customFetchBlob
          ? await props.customFetchBlob()
          : await getFileStream(props.fileId);
        const data = blob instanceof Blob ? blob : (blob as any)?.data;
        textContent.value = await data.text();
        break;
      }
      default:
        break;
    }
  } catch (err: any) {
    error.value = err?.message || '预览加载失败';
  } finally {
    loading.value = false;
  }
}

watch(() => props.fileId, loadPreview);
onMounted(loadPreview);
</script>

<template>
  <div class="preview-body">
    <div v-if="loading" class="preview-status">
      <span>加载中...</span>
    </div>
    <div v-else-if="error" class="preview-status">
      <p>{{ error }}</p>
    </div>
    <template v-else>
      <VueOfficePdf
        ref="pdfRef"
        v-if="previewType === 'pdf'"
        :src="previewUrl"
        class="preview-office"
      />
      <VueOfficeDocx
        v-if="previewType === 'docx'"
        :src="previewUrl"
        class="preview-office"
        :style="{ zoom: zoom ?? 1 }"
      />
      <pre
        v-if="previewType === 'text'"
        class="preview-text"
      >{{ textContent }}</pre>
      <img
        v-if="previewType === 'image'"
        :src="previewUrl"
        class="preview-image"
        alt="preview"
      />
      <video
        v-if="previewType === 'video'"
        :src="previewUrl"
        class="preview-media"
        controls
      />
      <audio
        v-if="previewType === 'audio'"
        :src="previewUrl"
        class="preview-audio"
        controls
      />
      <div
        v-if="previewType === 'unsupported'"
        class="preview-status"
      >
        暂不支持预览该文件类型
      </div>
    </template>
  </div>
</template>

<style scoped>
.preview-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.preview-status {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.preview-office {
  flex: 1;
  width: 100%;
  border: none;
}

.preview-text {
  flex: 1;
  margin: 0;
  padding: 16px;
  overflow: auto;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.preview-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  margin: 0 auto;
}

.preview-media {
  max-width: 100%;
  max-height: 100%;
  margin: 0 auto;
}

.preview-audio {
  width: 100%;
  margin-top: 40px;
}

</style>
