<template>
  <section class="milo-status" aria-label="米洛的工作状态">
    <div :class="['milo-status-bubble', current?.level || 'idle']" role="status" aria-live="polite" aria-atomic="true">
      <span class="milo-status-name">米洛</span>
      <p>{{ statusText }}</p>
    </div>
    <img src="/images/milo-welcome.png" alt="米洛" width="88" height="82">
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AgentProgressEvent, AgentProgressPhase } from '../types/task'

const props = defineProps<{ current: AgentProgressEvent | null }>()
const messages: Record<AgentProgressPhase, string> = {
  prompt_uploading: '正在整理分析所需的信息。',
  waiting_response: '正在等待分析结果，请稍等一下。',
  validating_response: '结果收到了，正在检查内容。',
  reflecting: '正在重新检查并尝试分析。',
  completed: '分析完成啦，来看看结果吧！',
  failed: '这次分析没有完成，请查看任务提示后重试。',
}
const statusText = computed(() => props.current ? messages[props.current.phase] : '我准备好啦，等你开始分析。')
</script>
