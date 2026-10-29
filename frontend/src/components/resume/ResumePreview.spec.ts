import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ResumePreview from './ResumePreview.vue'
import { projectResume } from '../../utils/resumeReview'
import type { RunArtifact } from '../../api/agentRuns'
describe('resume preview', () => {
 it('renders candidate content and its selected wording while excluding parsing and source metadata', () => {
  const wrapper = mount(ResumePreview, { props: { resume: { candidate_name: '林夏', contact: { email: 'lin@example.test' }, self_summary: '本人选择的简介', work_experience: [{ company: '小店', title: '工程师', description: '本人选择的经历', source_refs: [{ text: '原文隐私定位' }] }], skills: [{ name: 'Python', evidence_level: 'mentioned', source_refs: [] }], certifications: ['英语六级'], quality: { warning: '内部解析诊断' }, ambiguities: ['待澄清内部字段'], source_refs: [{ text: '内部引用' }] } } })
  expect(wrapper.text()).toContain('林夏'); expect(wrapper.text()).toContain('本人选择的简介'); expect(wrapper.text()).toContain('本人选择的经历'); expect(wrapper.text()).toContain('Python'); expect(wrapper.text()).toContain('英语六级')
  expect(wrapper.text()).not.toContain('source_refs'); expect(wrapper.text()).not.toContain('原文隐私定位'); expect(wrapper.text()).not.toContain('内部'); expect(wrapper.text()).not.toContain('mentioned')
 })
})


it.each(['draft', 'confirmed'])('keeps an explicitly cleared %s description empty instead of reviving its original bullets', (status) => {
 const artifact: RunArtifact = { id: 'v', runId: 'r', resumeId: 1, jdId: 2, revision: 2, status, reviewable: true, createdAt: '', factRefs: [], structuredContent: {
  resume: { work_experience: [{ company: '小店', description: '', bullets: [{ raw_text: '已清空的旧经历要点', source_refs: [] }] }] }, inputVersions: {},
  changes: [{ id: 'work', section: '/work_experience/0/description', before: '原始经历', after: '建议经历', reason: '突出职责', fact_refs: [], requires_input: false, status: 'edited', editedText: '' }],
 } }
 const preview = projectResume(artifact, { work: { id: 'work', status: 'edited', editedText: '' } })
 const wrapper = mount(ResumePreview, { props: { resume: preview } })
 expect(wrapper.text()).toContain('小店'); expect(wrapper.text()).not.toContain('已清空的旧经历要点'); expect(wrapper.text()).not.toContain('原始经历')
 expect((artifact.structuredContent.resume as { work_experience: { bullets: unknown[] }[] }).work_experience[0]!.bullets).toEqual([{ raw_text: '已清空的旧经历要点', source_refs: [] }])
})


it('keeps supported education advisers and independent experience bullets beside unedited descriptions', () => {
 const wrapper = mount(ResumePreview, { props: { resume: { education: [{ school: '示例大学', advisor: '图灵教授' }], work_experience: [{ company: '示例团队', description: '开发接口服务。', bullets: [{ raw_text: '接口延迟降低 30%。' }] }], projects: [{ name: '简历助手', description: '开发文档解析流程。', bullets: [{ raw_text: '加入 OCR 回退。' }] }] } } })
 expect(wrapper.text()).toContain('导师：图灵教授'); expect(wrapper.text()).toContain('开发接口服务。'); expect(wrapper.text()).toContain('接口延迟降低 30%。'); expect(wrapper.text()).toContain('开发文档解析流程。'); expect(wrapper.text()).toContain('加入 OCR 回退。')
})
