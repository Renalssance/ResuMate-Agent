import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { RunArtifact } from '../../api/agentRuns'
import ArtifactCard from './ArtifactCard.vue'

const resumeRef = { kind: 'resume', resumeId: 1, inputVersion: '2026-10-30T00:00:00+00:00', section: '/work_experience/0/description', sourceRefs: ['resume.pdf:p2'] }
const factRef = { kind: 'profile_fact', factId: 'fact-v2', revision: 2 }
const answerRef = { kind: 'applicant_answer', actionId: 'action-1' }
function artifact(): RunArtifact {
  return {
    id: 'draft-1', runId: 'run-1', resumeId: 1, jdId: 2, revision: 1, status: 'draft', createdAt: '',
    factRefs: [resumeRef, factRef, answerRef],
    structuredContent: {
      resume: { self_summary: '负责服务端开发。', work_experience: [{ description: '开发订单 API。' }] },
      inputVersions: { resume: '2026-10-30T00:00:00+00:00' },
      changes: [{ id: 'change-1', section: '/work_experience/0/description', before: '开发订单 API。', after: '负责订单 API 与数据库设计。', reason: '突出已经确认的职责。', fact_refs: [resumeRef, factRef], requires_input: false, status: 'pending' }],
    },
    sources: [
      { reference: resumeRef, label: '简历 · /work_experience/0/description', content: '开发订单 API。' },
      { reference: factRef, label: '已确认事实 · 第 2 版', content: { text: '负责数据库设计。' } },
      { reference: answerRef, label: '本次补充回答', content: { question: '无关问题', answers: { answer: '未被此建议引用的回答' } } },
    ],
    basedOnOldInput: false, changedInputs: [],
  } as RunArtifact
}

describe('evidence-based tailoring material', () => {
  it('shows the original and proposed field separately with its reason and only referenced sources', () => {
    const wrapper = mount(ArtifactCard, { props: { artifact: artifact() } })
    const change = wrapper.get('[aria-label="工作经历 1 · 经历说明建议"]')
    expect(change.get('[data-change-before]').text()).toBe('开发订单 API。')
    expect(change.get('[data-change-after]').text()).toBe('负责订单 API 与数据库设计。')
    expect(change.text()).toContain('突出已经确认的职责。')
    expect(change.text()).toContain('待审阅')
    expect(change.text()).toContain('负责数据库设计。')
    expect(change.text()).toContain('resume.pdf:p2')
    expect(change.text()).toContain('fact-v2')
    expect(change.text()).not.toContain('未被此建议引用的回答')
    expect(wrapper.text()).not.toContain('inputVersions')
    expect(wrapper.text()).not.toContain('条已确认事实')
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('keeps missing information visibly pending instead of rendering a fabricated replacement', () => {
    const value = artifact()
    value.structuredContent.changes = [{ id: 'missing', section: '/self_summary', before: '负责服务端开发。', after: null, reason: '需要补充项目中的具体职责。', fact_refs: [], requires_input: true, status: 'pending' }]
    const wrapper = mount(ArtifactCard, { props: { artifact: value } })
    const change = wrapper.get('[aria-label="个人简介建议"]')
    expect(change.text()).toContain('需补充信息')
    expect(change.get('[data-change-after]').text()).toContain('补充事实后再形成建议')
    expect(change.text()).toContain('需要补充项目中的具体职责。')
    expect(change.text()).not.toContain('null')
  })

  it('names changed inputs while showing the original source text and escaped applicant answer', () => {
    const value = artifact()
    Object.assign(value, { basedOnOldInput: true, changedInputs: ['resume', 'jd', 'facts'] })
    value.structuredContent.changes = [{ id: 'answer-change', section: '/self_summary', before: '负责服务端开发。', after: '参与数据库设计。', reason: '根据本次补充回答。', fact_refs: [answerRef], requires_input: false, status: 'pending' }]
    Object.assign(value, { sources: [{ reference: answerRef, label: '本次补充回答', content: { question: '具体职责？', answers: { answer: '<img src=x>参与数据库设计。' } } }] })
    const wrapper = mount(ArtifactCard, { props: { artifact: value } })
    const notice = wrapper.get('[role="note"]')
    expect(notice.text()).toContain('简历、岗位、已确认事实')
    expect(notice.text()).toContain('旧资料')
    expect(wrapper.text()).toContain('具体职责？')
    expect(wrapper.text()).toContain('<img src=x>参与数据库设计。')
    expect(wrapper.find('.source-content').text()).toContain('补充问题：具体职责？\n回答：<img src=x>参与数据库设计。')
    expect(wrapper.find('img').exists()).toBe(false)
  })

  it('reads historical material without interpreting an unrelated changes field as new suggestions', () => {
    const value = artifact()
    value.structuredContent = { summary: '历史简介。', changes: ['历史修改备注'] }
    const wrapper = mount(ArtifactCard, { props: { artifact: value } })
    expect(wrapper.text()).toContain('历史简介。')
    expect(wrapper.text()).toContain('历史修改备注')
    expect(wrapper.find('[aria-label="字段建议"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('条已确认事实')
  })
})
