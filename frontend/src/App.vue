<template>
  <RouterView v-if="route.meta.publicLayout" />
  <AppLayout v-else />
</template>

<script setup lang="ts">
import AppLayout from './components/AppLayout.vue'
import { useRoute } from 'vue-router'
const route = useRoute()
</script>
