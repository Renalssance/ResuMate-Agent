<template>
  <div class="markdown-content" :aria-busy="revealing" v-html="renderedHtml"></div>
</template>

<script setup lang="ts">
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { computed, onBeforeUnmount, ref, watch } from 'vue'

const props = withDefaults(defineProps<{ content: string; streaming?: boolean }>(), { streaming: false })
// Smooth incoming chunks over 250 ms, while keeping display backlog near 200 ms.
const RATE_SMOOTHING_MS = 250
const CATCH_UP_SECONDS = 0.2
const visibleContent = ref(props.content)
const revealing = ref(false)
let targetCharacters = Array.from(props.content)
let visibleCount = targetCharacters.length
let frame: number | undefined
let lastArrival: number | undefined
let lastFrame = 0
let arrivalRate = 40
let characterCredit = 0

function stopTimer() {
  if (frame !== undefined) cancelAnimationFrame(frame)
  frame = undefined
  characterCredit = 0
  revealing.value = false
}

function revealFrame(now: number) {
  frame = undefined
  const backlog = targetCharacters.length - visibleCount
  const speed = Math.max(12, arrivalRate, backlog / CATCH_UP_SECONDS)
  characterCredit += speed * Math.max(0, now - lastFrame) / 1000
  lastFrame = now
  const count = Math.min(backlog, Math.floor(characterCredit))
  if (count > 0) {
    visibleContent.value += targetCharacters.slice(visibleCount, visibleCount + count).join('')
    visibleCount += count
    characterCredit -= count
  }
  if (visibleCount >= targetCharacters.length) stopTimer()
  else frame = requestAnimationFrame(revealFrame)
}

function syncContent(content: string, streaming: boolean) {
  const appended = content.startsWith(targetCharacters.join(''))
  const previousLength = targetCharacters.length
  targetCharacters = Array.from(content)
  if (!streaming || !appended) {
    stopTimer()
    visibleContent.value = content
    visibleCount = targetCharacters.length
    lastArrival = undefined
    arrivalRate = 40
    return
  }
  const added = targetCharacters.length - previousLength
  const now = performance.now()
  if (added > 0) {
    if (lastArrival === undefined) arrivalRate = added / 0.1
    else {
      const elapsed = Math.max(16, now - lastArrival)
      const weight = 1 - Math.exp(-elapsed / RATE_SMOOTHING_MS)
      arrivalRate += weight * (added * 1000 / elapsed - arrivalRate)
    }
    lastArrival = now
  }
  if (visibleCount < targetCharacters.length && frame === undefined) {
    revealing.value = true
    lastFrame = now
    frame = requestAnimationFrame(revealFrame)
  }
}

function markNewestCharacter(html: string) {
  if (!revealing.value || !html || typeof DOMParser === 'undefined') return html
  const parsed = new DOMParser().parseFromString(html, 'text/html')
  const walker = parsed.createTreeWalker(parsed.body, 4)
  let current: Node | null = walker.nextNode()
  let lastText: Text | null = null
  while (current) {
    if (current.textContent?.trim()) lastText = current as Text
    current = walker.nextNode()
  }
  if (!lastText?.nodeValue) return html
  const characters = Array.from(lastText.nodeValue)
  let index = characters.length - 1
  while (index >= 0 && !characters[index]?.trim()) index--
  if (index < 0) return html
  const fragment = parsed.createDocumentFragment()
  fragment.append(characters.slice(0, index).join(''))
  const newest = parsed.createElement('span')
  newest.className = 'stream-char'
  newest.textContent = characters[index] || ''
  fragment.append(newest, characters.slice(index + 1).join(''))
  lastText.replaceWith(fragment)
  return parsed.body.innerHTML
}

const renderedHtml = computed(() => {
  const parsed = marked.parse(visibleContent.value, { async: false, breaks: true, gfm: true }) as string
  return markNewestCharacter(DOMPurify.sanitize(parsed))
})

watch([() => props.content, () => props.streaming], ([content, streaming]) => syncContent(content, streaming), { flush: 'sync' })
onBeforeUnmount(stopTimer)
</script>
