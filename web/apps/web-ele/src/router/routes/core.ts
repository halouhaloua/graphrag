import type { RouteRecordRaw } from 'vue-router';

import { LOGIN_PATH } from '@vben/constants';
import { preferences } from '@vben/preferences';

import { $t } from '#/locales';

const BasicLayout = () => import('#/layouts/basic.vue');
const AuthPageLayout = () => import('#/layouts/auth.vue');
/** 全局404页面 */
const fallbackNotFoundRoute: RouteRecordRaw = {
  component: () => import('#/views/_core/fallback/not-found.vue'),
  meta: {
    hideInBreadcrumb: true,
    hideInMenu: true,
    hideInTab: true,
    title: '404',
  },
  name: 'FallbackNotFound',
  path: '/:path(.*)*',
};

/** 基本路由，这些路由是必须存在的 */
const coreRoutes: RouteRecordRaw[] = [
  /**
   * 根路由
   * 使用基础布局，作为所有页面的父级容器，子级就不必配置BasicLayout。
   * 此路由必须存在，且不应修改
   */
  {
    component: BasicLayout,
    meta: {
      hideInBreadcrumb: true,
      title: 'Root',
    },
    name: 'Root',
    path: '/',
    redirect: preferences.app.defaultHomePath,
    children: [
      // RAG 隐藏子页面（不在菜单中显示，通过 router.push 跳转）
      {
        name: 'KnowledgeBaseDetail',
        path: 'rag/knowledge-base/:kbId',
        component: () => import('#/views/_core/rag/detail/index.vue'),
        meta: { hideInMenu: true, title: '知识库详情' },
      },
      {
        name: 'KbFilePreview',
        path: 'rag/knowledge-base/:kbId/files/:fileId/preview',
        component: () => import('#/views/_core/rag/kb-preview.vue'),
        meta: { hideInMenu: true, title: '知识库文件预览' },
      },
      {
        name: 'RagFileTask',
        path: 'rag/file-manager/:fileId/task',
        component: () => import('#/views/_core/rag/file-manager/task.vue'),
        meta: { hideInMenu: true, title: '文件编辑' },
      },
      {
        name: 'KbFileEditTask',
        path: 'rag/kb-file/:fileId/task',
        component: () => import('#/views/_core/rag/file-manager/kb-task.vue'),
        meta: { hideInMenu: true, title: '知识库文件编辑' },
      },
    ],
  },
  {
    component: AuthPageLayout,
    meta: {
      hideInTab: true,
      title: 'Authentication',
    },
    name: 'Authentication',
    path: '/auth',
    redirect: LOGIN_PATH,
    children: [
      {
        name: 'Login',
        path: 'login',
        component: () => import('#/views/_core/authentication/login.vue'),
        meta: {
          title: $t('page.auth.login'),
        },
      },
      {
        name: 'CodeLogin',
        path: 'code-login',
        component: () => import('#/views/_core/authentication/code-login.vue'),
        meta: {
          title: $t('page.auth.codeLogin'),
        },
      },
      {
        name: 'QrCodeLogin',
        path: 'qrcode-login',
        component: () =>
          import('#/views/_core/authentication/qrcode-login.vue'),
        meta: {
          title: $t('page.auth.qrcodeLogin'),
        },
      },
      {
        name: 'ForgetPassword',
        path: 'forget-password',
        component: () =>
          import('#/views/_core/authentication/forget-password.vue'),
        meta: {
          title: $t('page.auth.forgetPassword'),
        },
      },
      {
        name: 'Register',
        path: 'register',
        component: () => import('#/views/_core/authentication/register.vue'),
        meta: {
          title: $t('page.auth.register'),
        },
      },
    ],
  },
  // OAuth 回调路由（独立路由，不在 auth 布局下，支持多个提供商）
  {
    name: 'OAuthCallback',
    path: '/oauth/:provider/callback',
    component: () => import('#/views/_core/authentication/oauth-callback.vue'),
    meta: {
      hideInBreadcrumb: true,
      hideInMenu: true,
      hideInTab: true,
      title: 'OAuth 登录回调',
    },
  },
  // 文件预览
  {
    name: 'FilePreview',
    path: '/file-preview/:id',
    component: () => import('#/views/_core/file-preview/index.vue'),
    meta: {
      hideInBreadcrumb: true,
      hideInMenu: true,
      hideInTab: true,
      title: '文件预览',
    },
  },
  // AI工作流编辑器（全屏，不使用 BasicLayout）
  {
    name: 'AiWorkflowDetail',
    path: '/ai-platform/workflow/:id',
    component: () => import('#/views/_core/ai-workflow/detail.vue'),
    meta: { hideInMenu: true, hideInTab: true, title: '工作流编辑器' },
  },
  // 表单页面 - 新增（主应用）
  {
    name: 'FormPageAdd',
    path: '/form-render/:code/add',
    component: () => import('#/views/online-dev/form-render/form-page.vue'),
    meta: {
      hideInBreadcrumb: true,
      hideInMenu: true,
      title: '新增表单',
    },
  },
  // 表单页面 - 编辑（主应用）
  {
    name: 'FormPageEdit',
    path: '/form-render/:code/edit/:id',
    component: () => import('#/views/online-dev/form-render/form-page.vue'),
    meta: {
      hideInBreadcrumb: true,
      hideInMenu: true,
      title: '编辑表单',
    },
  },
  // 表单页面 - 查看（主应用）
  {
    name: 'FormPageView',
    path: '/form-render/:code/view/:id',
    component: () => import('#/views/online-dev/form-render/form-page.vue'),
    meta: {
      hideInBreadcrumb: true,
      hideInMenu: true,
      title: '查看表单',
    },
  },
  // 表单页面 - 新增（子应用）
  {
    name: 'SubAppFormPageAdd',
    path: '/app/:appCode/form-render/:code/add',
    component: () => import('#/views/online-dev/form-render/form-page.vue'),
    meta: {
      hideInBreadcrumb: true,
      hideInMenu: true,
      title: '新增表单',
    },
  },
  // 表单页面 - 编辑（子应用）
  {
    name: 'SubAppFormPageEdit',
    path: '/app/:appCode/form-render/:code/edit/:id',
    component: () => import('#/views/online-dev/form-render/form-page.vue'),
    meta: {
      hideInBreadcrumb: true,
      hideInMenu: true,
      title: '编辑表单',
    },
  },
  // 表单页面 - 查看（子应用）
  {
    name: 'SubAppFormPageView',
    path: '/app/:appCode/form-render/:code/view/:id',
    component: () => import('#/views/online-dev/form-render/form-page.vue'),
    meta: {
      hideInBreadcrumb: true,
      hideInMenu: true,
      title: '查看表单',
    },
  },
  // 表单页面 - 新增（子应用开发模式）
  {
    name: 'SubAppDevFormPageAdd',
    path: '/app-dev/:appCode/form-render/:code/add',
    component: () => import('#/views/online-dev/form-render/form-page.vue'),
    meta: {
      hideInBreadcrumb: true,
      hideInMenu: true,
      title: '新增表单',
    },
  },
  // 表单页面 - 编辑（子应用开发模式）
  {
    name: 'SubAppDevFormPageEdit',
    path: '/app-dev/:appCode/form-render/:code/edit/:id',
    component: () => import('#/views/online-dev/form-render/form-page.vue'),
    meta: {
      hideInBreadcrumb: true,
      hideInMenu: true,
      title: '编辑表单',
    },
  },
  // 表单页面 - 查看（子应用开发模式）
  {
    name: 'SubAppDevFormPageView',
    path: '/app-dev/:appCode/form-render/:code/view/:id',
    component: () => import('#/views/online-dev/form-render/form-page.vue'),
    meta: {
      hideInBreadcrumb: true,
      hideInMenu: true,
      title: '查看表单',
    },
  },
];

export { coreRoutes, fallbackNotFoundRoute };
