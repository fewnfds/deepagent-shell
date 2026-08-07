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
  <div class="graph-node" :data-status="data.status || undefined">
    <div class="graph-node__header">
      <div class="graph-node__title text-break">{{ data.label }}</div>
      <div class="graph-node__type font-monospace text-break">{{ data.type }}</div>
    </div>
    <div class="graph-node__ports">
      <div v-for="port in data.input_ports ?? []" :key="`in-${port}`" class="graph-node__port-row graph-node__port-row--input">
        <Handle :id="port" type="target" :position="Position.Left" :connectable="true" class="graph-node__handle" />
        <span class="graph-node__port-name font-monospace">{{ port }}</span>
      </div>
      <div v-for="port in data.output_ports ?? []" :key="`out-${port}`" class="graph-node__port-row graph-node__port-row--output">
        <span class="graph-node__port-name font-monospace">{{ port }}</span>
        <Handle :id="port" type="source" :position="Position.Right" :connectable="true" class="graph-node__handle" />
      </div>
    </div>
    <div v-if="data.status" class="graph-node__status text-uppercase">{{ data.status }}</div>
  </div>
</template>
