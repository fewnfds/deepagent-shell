<script setup lang="ts">
import { computed, ref } from 'vue'
import type { WorkflowNodeCatalogItem } from '@/api'

const props = defineProps<{ catalog: WorkflowNodeCatalogItem[] }>()
const emit = defineEmits<{ add: [type: string] }>()
const query = ref('')
const category = ref('all')

const categories = computed(() => {
  const values = new Set(props.catalog.map((item) => item.execution_kind || 'node'))
  return ['all', ...values]
})
const filtered = computed(() => {
  const needle = query.value.trim().toLowerCase()
  return props.catalog.filter((item) => {
    const matchesCategory = category.value === 'all' || (item.execution_kind || 'node') === category.value
    const haystack = `${item.title} ${item.type} ${item.execution_kind}`.toLowerCase()
    return matchesCategory && (!needle || haystack.includes(needle))
  })
})

function onDragStart(event: DragEvent, type: string): void {
  event.dataTransfer?.setData('application/x-agent-shell-node', type)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'copy'
}
</script>

<template>
  <aside class="workspace-panel workspace-panel--palette" aria-label="Node palette">
    <div class="workspace-panel__header">
      <div>
        <div class="workspace-panel__eyebrow">GRAPH COMPONENTS</div>
        <h2 class="workspace-panel__title">节点库</h2>
      </div>
      <span class="badge text-bg-secondary">{{ filtered.length }}</span>
    </div>
    <div class="workspace-panel__body">
      <div class="input-group input-group-sm mb-2">
        <span class="input-group-text"><i class="bi bi-search" aria-hidden="true" /></span>
        <input v-model="query" class="form-control" type="search" placeholder="搜索节点" aria-label="搜索节点">
      </div>
      <div class="workspace-palette__categories mb-2" role="list" aria-label="节点分类">
        <button
          v-for="item in categories"
          :key="item"
          class="btn btn-sm btn-outline-secondary"
          :data-active="category === item || undefined"
          type="button"
          @click="category = item"
        >
          {{ item === 'all' ? '全部' : item }}
        </button>
      </div>
      <div class="workspace-palette__list">
        <button
          v-for="item in filtered"
          :key="item.type"
          class="workspace-palette__item"
          draggable="true"
          type="button"
          @click="emit('add', item.type)"
          @dragstart="onDragStart($event, item.type)"
        >
          <span class="workspace-palette__item-icon"><i class="bi bi-boxes" aria-hidden="true" /></span>
          <span class="workspace-palette__item-copy">
            <strong>{{ item.title }}</strong>
            <small class="font-monospace">{{ item.type }}</small>
          </span>
          <i class="bi bi-plus-lg" aria-hidden="true" />
        </button>
        <p v-if="!filtered.length" class="small text-body-secondary mb-0">没有匹配的节点。</p>
      </div>
    </div>
  </aside>
</template>
