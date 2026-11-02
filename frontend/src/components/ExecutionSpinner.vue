<template>
  <LoaderCircle class="execution-spinner" aria-hidden="true" />
</template>

<script setup lang="ts">
import { LoaderCircle } from '@lucide/vue'
</script>

<style scoped>
.execution-spinner { width: 1em; height: 1em; flex-shrink: 0; animation: execution-spin 800ms linear infinite; }
@keyframes execution-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .execution-spinner { animation: none; } }
</style>
