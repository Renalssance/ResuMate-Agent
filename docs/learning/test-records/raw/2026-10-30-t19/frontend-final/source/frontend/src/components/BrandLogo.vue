<template>
  <RouterLink class="rm-brand" to="/" aria-label="ResuMate 首页">
    <Cat :size="30" :stroke-width="2.2" aria-hidden="true" />
    <span>ResuMate<span class="rm-brand-dot">.</span></span>
  </RouterLink>
</template>

<script setup lang="ts">
import { Cat } from '@lucide/vue'
</script>
