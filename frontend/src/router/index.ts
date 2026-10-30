import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.meta.publicLayout || from.meta.publicLayout) {
      return to.hash ? { el: to.hash } : { top: 0 }
    }
  },
  routes: [
    { path: '/', name: 'home', component: () => import('../views/HomeView.vue'), meta: { title: '你的招聘好伙伴', publicLayout: true } },
    { path: '/login', name: 'login', component: () => import('../views/AuthView.vue'), meta: { title: '登录', publicLayout: true } },
    { path: '/register', name: 'register', component: () => import('../views/AuthView.vue'), meta: { title: '注册', publicLayout: true } },
    {
      path: '/documents',
      name: 'documents',
      component: () => import('../views/DocumentsView.vue'),
      meta: { title: '文档管理', description: '上传、解析、查看和删除 JD 与简历' },
    },
    { path: '/interviews/:id', name: 'interview', component: () => import('../views/InterviewView.vue'), meta: { title: '模拟面试', description: '基于本次投递材料，练习回答并回顾反馈' } },
    { path: '/jobs', name: 'jobs', component: () => import('../views/JobsView.vue'), meta: { title: '岗位中心', description: '收藏岗位原文、关联简历并准备投递材料' } },
    { path: '/resume-versions/:versionId', name: 'resume-editor', component: () => import('../views/ResumeEditorView.vue'), meta: { title: '审阅与编辑', description: '逐条核对建议，保存并确认属于你的简历版本' } },
    { path: '/agent/tasks/:runId?', name: 'agent-tasks', component: () => import('../views/AgentTaskView.vue'), meta: { title: '材料准备', description: '准备、补充并核对你的投递材料' } },
    {
      path: '/matching',
      name: 'matching',
      component: () => import('../views/MatchingView.vue'),
      meta: { title: '岗位匹配', description: '选择 JD 和简历，运行匹配 Agent' },
    },
    {
      path: '/profile-fields',
      name: 'profile-fields',
      component: () => import('../views/ProfileFieldsView.vue'),
      meta: { title: '结构资料', description: '查看、补充并保存招聘表单常用字段' },
    },
    {
      path: '/questions',
      name: 'questions',
      component: () => import('../views/QuestionsView.vue'),
      meta: { title: '试题生成', description: '基于岗位和候选人生成面试试题' },
    },
    {
      path: '/applications',
      name: 'applications',
      component: () => import('../views/ApplicationsView.vue'),
      meta: { title: '投递记录', description: '记录公司、岗位、投递日期和进展状态' },
    },
    {
      path: '/extension',
      name: 'extension',
      component: () => import('../views/ExtensionView.vue'),
      meta: { title: '浏览器插件', description: '下载并安装 ResuMate Autofill，辅助填写招聘表单' },
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../views/SettingsView.vue'),
      meta: { title: '设置', description: '管理模型参数和调用统计' },
    },
  ],
})

router.afterEach((to) => {
  document.title = `${to.meta.title || '你的招聘好伙伴'} · ResuMate`
})

export default router
