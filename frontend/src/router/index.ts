import { createRouter, createWebHistory } from 'vue-router'
import DocumentsView from '../views/DocumentsView.vue'
import MatchingView from '../views/MatchingView.vue'
import QuestionsView from '../views/QuestionsView.vue'
import FollowUpView from '../views/FollowUpView.vue'

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
      path: '/questions',
      name: 'questions',
      component: QuestionsView,
      meta: { title: '试题生成', description: '基于岗位和候选人生成面试试题' },
    },
    {
      path: '/follow-up',
      name: 'follow-up',
      component: FollowUpView,
      meta: { title: '追问模拟', description: '根据候选人回答生成下一轮追问' },
    },
  ],
})

export default router
