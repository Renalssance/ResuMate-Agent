import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import TaskProgress from './TaskProgress.vue'

const props = {
  title: '解析简历', taskId: 'task-1', progress: 25, currentStep: '读取文档',
  completedCount: 0, message: '正在读取', errorReason: '',
  steps: [{ key: 'extract', label: '文本提取', status: 'running' as const, progress: 50 }],
}

describe('任务进度的可见状态', () => {
  it('没有任务时不显示旧进度', () => {
    const wrapper = mount(TaskProgress, { props: { ...props, taskId: '' } })
    expect(wrapper.find('section').exists()).toBe(false)
    wrapper.unmount()
  })

  it('收到失败状态后展示失败步骤和可供排查的原因', async () => {
    const wrapper = mount(TaskProgress, { props })
    expect(wrapper.text()).toContain('进行中 50%')
    expect(wrapper.find('.error-note').exists()).toBe(false)
    await wrapper.setProps({
      steps: [{ key: 'extract', label: '文本提取', status: 'failed', progress: 50 }],
      errorReason: '文档无法读取',
    })
    expect(wrapper.find('.parse-step-item.failed').text()).toContain('失败')
    expect(wrapper.find('.error-note').text()).toContain('文档无法读取')
    wrapper.unmount()
  })
})
