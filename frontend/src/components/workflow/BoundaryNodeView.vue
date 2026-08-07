<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'

defineProps<{
  data: {
    label: string
    type: string
    input_ports?: string[]
    output_ports?: string[]
    boundary?: 'api' | 'entry'
  }
}>()
</script>

<template>
  <div class="graph-boundary-node" :data-boundary="data.boundary">
    <div class="graph-boundary-node__eyebrow">BOUNDARY</div>
    <div class="graph-boundary-node__title text-break">{{ data.label }}</div>
    <div class="graph-boundary-node__type font-monospace text-break">{{ data.type }}</div>
    <div v-for="port in data.input_ports ?? []" :key="`in-${port}`" class="graph-boundary-node__port graph-boundary-node__port--input font-monospace">
      <Handle :id="port" type="target" :position="Position.Left" class="graph-boundary-node__handle" />
      {{ port }}
    </div>
    <div v-for="port in data.output_ports ?? []" :key="`out-${port}`" class="graph-boundary-node__port graph-boundary-node__port--output font-monospace">
      {{ port }}
      <Handle :id="port" type="source" :position="Position.Right" class="graph-boundary-node__handle" />
    </div>
  </div>
</template>
