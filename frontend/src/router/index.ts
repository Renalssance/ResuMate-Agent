import { createRouter, createWebHistory } from 'vue-router'
import DocumentsView from '../views/DocumentsView.vue'
import ExtensionView from '../views/ExtensionView.vue'
import MatchingView from '../views/MatchingView.vue'
import ProfileFieldsView from '../views/ProfileFieldsView.vue'
import QuestionsView from '../views/QuestionsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/documents' },
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
      path: '/extension',
      name: 'extension',
      component: ExtensionView,
      meta: { title: '浏览器插件', description: '下载并安装 ResuMate Autofill，辅助填写招聘表单' },
    },
  ],
})

export default router
