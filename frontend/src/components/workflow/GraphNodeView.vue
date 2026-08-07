<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'

defineProps<{
  data: {
    label: string
    type: string
    status?: string
    input_ports?: string[]
    output_ports?: string[]
  }
}>()
</script>

<template>
  <div class="graph-node p-2" :data-status="data.status || undefined">
    <Handle
      v-for="port in data.input_ports ?? []"
      :id="port"
      :key="`in-${port}`"
      type="target"
      :position="Position.Left"
      class="graph-node__handle"
    />
    <div class="graph-node__title text-break">{{ data.label }}</div>
    <div class="graph-node__type font-monospace text-break">{{ data.type }}</div>
    <div v-if="data.status" class="graph-node__status text-uppercase">{{ data.status }}</div>
    <Handle
      v-for="port in data.output_ports ?? []"
      :id="port"
      :key="`out-${port}`"
      type="source"
      :position="Position.Right"
      class="graph-node__handle"
    />
  </div>
</template>
