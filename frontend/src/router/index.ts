import { createRouter, createWebHistory } from 'vue-router'
import ApplicationsView from '../views/ApplicationsView.vue'
import DocumentsView from '../views/DocumentsView.vue'
import ExtensionView from '../views/ExtensionView.vue'
import MatchingView from '../views/MatchingView.vue'
import ProfileFieldsView from '../views/ProfileFieldsView.vue'
import QuestionsView from '../views/QuestionsView.vue'
import SettingsView from '../views/SettingsView.vue'
import HomeView from '../views/HomeView.vue'
import AuthView from '../views/AuthView.vue'

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.meta.publicLayout || from.meta.publicLayout) {
      return to.hash ? { el: to.hash } : { top: 0 }
    }
  },
  routes: [
    { path: '/', name: 'home', component: HomeView, meta: { title: '你的招聘好伙伴', publicLayout: true } },
    { path: '/login', name: 'login', component: AuthView, meta: { title: '登录', publicLayout: true } },
    { path: '/register', name: 'register', component: AuthView, meta: { title: '注册', publicLayout: true } },
    {
      path: '/documents',
      name: 'documents',
      component: DocumentsView,
      meta: { title: '文档管理', description: '上传、解析、查看和删除 JD 与简历' },
    },
    {
      path: '/matching',
      name: 'matching',
      component: MatchingView,
      meta: { title: '岗位匹配', description: '选择 JD 和简历，运行匹配 Agent' },
    },
    {
      path: '/profile-fields',
      name: 'profile-fields',
      component: ProfileFieldsView,
      meta: { title: '结构资料', description: '查看、补充并保存招聘表单常用字段' },
    },
    {
      path: '/questions',
      name: 'questions',
      component: QuestionsView,
      meta: { title: '试题生成', description: '基于岗位和候选人生成面试试题' },
    },
    {
      path: '/applications',
      name: 'applications',
      component: ApplicationsView,
      meta: { title: '投递记录', description: '记录公司、岗位、投递日期和进展状态' },
    },
    {
      path: '/extension',
      name: 'extension',
      component: ExtensionView,
      meta: { title: '浏览器插件', description: '下载并安装 ResuMate Autofill，辅助填写招聘表单' },
    },
    {
      path: '/settings',
      name: 'settings',
      component: SettingsView,
      meta: { title: '设置', description: '管理模型参数和调用统计' },
    },
  ],
})

router.afterEach((to) => {
  document.title = `${to.meta.title || '你的招聘好伙伴'} · ResuMate`
})

export default router
