<template>
  <div class="milo-mascot">
    <img v-show="!ready" src="/images/milo-welcome.png" alt="蓝眼睛的暹罗猫米洛，举爪欢迎你，怀抱一份简历" width="1312" height="1199" fetchpriority="high" draggable="false">
    <canvas v-show="ready" ref="canvas" role="img" aria-label="蓝眼睛的米洛随鼠标轻轻转动视线，怀抱一份简历"></canvas>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

const canvas = ref<HTMLCanvasElement | null>(null)
const ready = ref(false)
let dispose = () => {}

type Layer = { x: number; y: number; w: number; h: number; image: HTMLImageElement }
const W = 1312, H = 1199

onMounted(() => {
  const element = canvas.value!
  const ctx = element.getContext('2d')
  if (!ctx) return
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)')
  const pointer = window.matchMedia('(hover: hover) and (pointer: fine)')
  let disposed = false, visible = true, frame = 0, previous = 0, clock = 0
  let target = [0, 0], head = [0, 0], gaze = [0, 0], velocity = [0, 0]
  let base: HTMLImageElement
  let layers: Record<string, Layer> = {}

  function part(name: string, x = 0, y = 0) {
    const layer = layers[name]!
    ctx!.drawImage(layer.image, layer.x + x, layer.y + y)
  }
  function draw() {
    if (!ready.value) return
    ctx!.setTransform(1, 0, 0, 1, 0, 0)
    ctx!.clearRect(0, 0, element.width, element.height)
    const scale = Math.min(element.width / W, element.height / H) * .92
    ctx!.translate((element.width - W * scale) / 2, (element.height - H * scale) / 2)
    ctx!.scale(scale, scale)
    const x = head[0]!, y = head[1]!
    const breath = reduce.matches ? 0 : Math.sin(clock * 1.25) * 3
    ctx!.translate(W / 2, 950 - breath)
    ctx!.rotate(x * .018)
    ctx!.translate(-W / 2, -950)
    ctx!.drawImage(base, 0, 0, W, H)
    // Selected preview: gaze follow at amplitude 1.0. Cutouts never stretch.
    for (const side of ['left', 'right']) {
      part(side + '-eye', x * 5, y * 3)
      part(side + '-iris', x * 5 + gaze[0]! * 5, y * 3 + gaze[1]! * 4)
    }
    part('nose', x * 8, y * 5)
    ctx!.save()
    ctx!.translate(760 + x * 2, 880 + y)
    ctx!.rotate(x * .006)
    ctx!.translate(-760, -880)
    // Keep paper and holding paw rigidly attached.
    part('resume'); part('paw')
    ctx!.restore()
  }
  function tick(time: number) {
    if (reduce.matches) { syncMotion(); return }
    const dt = Math.min((time - previous) / 1000 || .016, 1 / 30)
    previous = time; clock += dt
    for (let i = 0; i < 2; i++) {
      velocity[i] = velocity[i]! + ((target[i]! - head[i]!) * 100 - velocity[i]! * 16) * dt
      head[i] = head[i]! + velocity[i]! * dt
      gaze[i] = gaze[i]! + (target[i]! - gaze[i]!) * (1 - Math.exp(-18 * dt))
    }
    draw(); frame = requestAnimationFrame(tick)
  }
  function syncMotion() {
    cancelAnimationFrame(frame)
    frame = 0
    if (!ready.value || disposed) return
    if (reduce.matches || !pointer.matches) {
      target = [0, 0]; head = [0, 0]; gaze = [0, 0]; velocity = [0, 0]
      draw()
    }
    if (!reduce.matches && visible && !document.hidden) {
      previous = performance.now(); frame = requestAnimationFrame(tick)
    }
  }
  function resize() {
    const rect = element.parentElement!.getBoundingClientRect()
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    element.width = Math.round(rect.width * dpr)
    element.height = Math.round(rect.height * dpr)
    draw()
  }
  function move(event: PointerEvent) {
    if (reduce.matches || !pointer.matches || !visible || event.pointerType !== 'mouse') return
    const rect = element.getBoundingClientRect()
    target = [Math.max(-1, Math.min(1, (event.clientX - rect.left - rect.width / 2) / (rect.width * .5))), Math.max(-1, Math.min(1, (event.clientY - rect.top - rect.height / 2) / (rect.height * .5)))]
  }
  function reset() { target = [0, 0] }
  const resizeObserver = new ResizeObserver(resize)
  resizeObserver.observe(element.parentElement!)
  const intersectionObserver = new IntersectionObserver(([entry]) => {
    visible = entry!.isIntersecting
    if (!visible) reset()
    syncMotion()
  })
  intersectionObserver.observe(element.parentElement!)
  window.addEventListener('pointermove', move, { passive: true })
  window.addEventListener('blur', reset)
  document.documentElement.addEventListener('pointerleave', reset)
  document.addEventListener('visibilitychange', syncMotion)
  reduce.addEventListener('change', syncMotion)
  pointer.addEventListener('change', syncMotion)
  dispose = () => {
    disposed = true; cancelAnimationFrame(frame)
    resizeObserver.disconnect(); intersectionObserver.disconnect()
    window.removeEventListener('pointermove', move)
    window.removeEventListener('blur', reset)
    document.documentElement.removeEventListener('pointerleave', reset)
    document.removeEventListener('visibilitychange', syncMotion)
    reduce.removeEventListener('change', syncMotion)
    pointer.removeEventListener('change', syncMotion)
  }
  async function image(src: string) {
    const img = new Image(); img.src = src; await img.decode(); return img
  }
  async function load() {
    try {
      const response = await fetch('/images/milo-layers/manifest.json')
      if (!response.ok) return
      const manifest: Record<string, Omit<Layer, 'image'>> = await response.json()
      const [plate, parts] = await Promise.all([
        image('/images/milo-layers/clean-plate.png'),
        Promise.all(Object.entries(manifest).map(async ([name, rect]) => [name, { ...rect, image: await image(`/images/milo-layers/${name}.png`) }] as const)),
      ])
      if (disposed) return
      base = plate; layers = Object.fromEntries(parts); ready.value = true
      resize(); syncMotion()
    } catch {
      // Keep the original mascot visible if any layer cannot load.
    }
  }
  void load()
})
onUnmounted(() => dispose())
</script>

<style scoped>
.milo-mascot { position: relative; z-index: 1; width: 100%; aspect-ratio: 1312 / 1199; }
.milo-mascot img, .milo-mascot canvas { position: absolute; inset: 0; display: block; width: 100%; height: 100%; }
</style>
