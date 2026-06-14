import { computed, onMounted, onUnmounted, ref } from 'vue'

export function useResponsive() {
  const width = ref(window.innerWidth)
  const update = () => {
    width.value = window.innerWidth
  }

  onMounted(() => window.addEventListener('resize', update))
  onUnmounted(() => window.removeEventListener('resize', update))

  return {
    width,
    isMobile: computed(() => width.value < 768),
    isTablet: computed(() => width.value >= 768 && width.value < 1200),
  }
}
