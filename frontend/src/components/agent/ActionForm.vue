<template>
  <form class="action-form" @submit.prevent="submit('submit')">
    <template v-if="action.kind === 'input'">
      <fieldset v-if="documentType" :disabled="busy || inactive" :aria-describedby="error ? errorId : undefined">
        <legend>{{ question }}</legend>
        <p>{{ action.payload.filename }}</p>
        <label><input type="radio" :name="fieldId" value="resume" :checked="modelValue === 'resume'" @change="emit('update:modelValue', 'resume')">简历</label>
        <label><input type="radio" :name="fieldId" value="jd" :checked="modelValue === 'jd'" @change="emit('update:modelValue', 'jd')">岗位</label>
      </fieldset>
      <template v-else>
        <label :for="fieldId">{{ question }}</label>
        <textarea :id="fieldId" ref="answerField" :value="modelValue" rows="4" :readonly="inactive" :disabled="busy" :aria-invalid="Boolean(error)" :aria-describedby="error ? errorId : undefined" @input="$emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"></textarea>
      </template>
    </template>
    <p v-else>{{ question }}</p>
    <p v-if="inactive" class="muted-note">任务状态已变化。以下回答尚未提交，供你核对。</p>
    <p v-if="error" :id="errorId" class="error-note" role="alert">{{ error }}</p>
    <div v-if="!inactive" class="action-buttons">
      <button v-if="action.kind === 'input'" class="button-primary" type="submit" :disabled="busy">{{ busy ? '正在提交…' : '继续任务' }}</button>
      <template v-else>
        <button class="button-primary" type="button" :disabled="busy" @click="submit('approve')">确认并继续</button>
        <button class="button-secondary" type="button" :disabled="busy" @click="submit('reject')">拒绝并结束</button>
      </template>
    </div>
  </form>
</template>
<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { RunAction } from '../../api/agentRuns'
const props = withDefaults(defineProps<{ action: RunAction; modelValue: string; busy: boolean; error: string; inactive?: boolean; documentType?: boolean }>(), { inactive: false, documentType: false })
const emit = defineEmits<{ 'update:modelValue': [value: string]; submit: [decision: 'submit' | 'approve' | 'reject'] }>()
const fieldId = computed(() => `answer-${props.action.actionId}`), errorId = computed(() => `${fieldId.value}-error`)
const question = computed(() => String(props.action.payload.question || (props.action.kind === 'approval' ? '请审阅本次材料并确认是否继续' : '请补充你的实际经历')))
const answerField = ref<HTMLTextAreaElement | null>(null)
function submit(decision: 'submit' | 'approve' | 'reject') { if (!props.busy && !props.inactive) emit('submit', decision) }
watch(() => props.error, async (error) => { if (error) { await nextTick(); answerField.value?.focus() } })
watch(() => props.busy, async (busy, previous) => { if (previous && !busy) { await nextTick(); answerField.value?.focus() } })
</script>
<style scoped>
.action-form { display: grid; gap: 12px; padding: 20px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--surface-panel-soft); }
fieldset { border: 0; padding: 0; min-width: 0; } fieldset label { display: inline-flex; align-items: center; gap: 6px; margin-right: 20px; min-height: 40px; } legend { font-weight: 600; } fieldset p { overflow-wrap: anywhere; }
label { font-weight: 600; overflow-wrap: anywhere; } textarea { width: 100%; resize: vertical; min-height: 110px; } .action-buttons { display: flex; flex-wrap: wrap; gap: 10px; } .muted-note { color: var(--color-text-secondary); }
</style>
