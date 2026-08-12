<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import type { CapabilityManifest, WorkflowComponentManifest } from '@/api'
import SectionNav from '@/components/SectionNav.vue'
import type { SectionNavItem } from '@/components/sectionNav'
import { agentLibraryCategories, routeCategory } from '@/pages/configLibrary'

const props = defineProps<{
  manifests: readonly (CapabilityManifest | WorkflowComponentManifest)[]
}>()

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const activeCategoryId = computed(() => routeCategory(route.params.type))
const componentItems = computed<SectionNavItem[]>(() => props.manifests.map((manifest) => ({
  id: manifest.type,
  label: t(`capabilities.${manifest.type}.label`),
})))
const agentItems = computed<SectionNavItem[]>(() => agentLibraryCategories.map((id) => ({
  id,
  label: t(`capabilities.${id}.label`),
})))

function selectCategory(id: string): void {
  if (id === activeCategoryId.value) return
  void router.push(`/library/${encodeURIComponent(id)}`)
}
</script>

<template>
  <div
    v-if="componentItems.length"
    class="d-flex flex-wrap align-items-center gap-2 mb-2"
    data-testid="library-component-group"
  >
    <span class="fw-semibold">{{ t('library.groups.components') }}</span>
    <SectionNav
      :active-id="activeCategoryId"
      :aria-label="t('library.groups.components')"
      :items="componentItems"
      layout="inline"
      @select="selectCategory"
    />
  </div>
  <div class="d-flex flex-wrap align-items-center gap-2 mb-2" data-testid="library-agent-group">
    <span class="fw-semibold">{{ t('library.groups.agents') }}</span>
    <SectionNav
      :active-id="activeCategoryId"
      :aria-label="t('library.groups.agents')"
      :items="agentItems"
      layout="inline"
      @select="selectCategory"
    />
  </div>
</template>
