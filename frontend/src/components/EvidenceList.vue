<template>
  <div class="evidence-list">
    <article v-for="item in items" :key="item">
      {{ item }}
    </article>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  items: string[]
}>()
</script>
