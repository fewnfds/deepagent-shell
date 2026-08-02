import { createRouter, createWebHashHistory } from 'vue-router'

const AgentSessionsPage = () => import('@/pages/AgentSessionsPage.vue')
const ApiServerSettingsPage = () => import('@/pages/ApiServerSettingsPage.vue')
const ComponentsPage = () => import('@/pages/ComponentsPage.vue')
const ConfigLibraryPage = () => import('@/pages/ConfigLibraryPage.vue')
const EventFeedPage = () => import('@/pages/EventFeedPage.vue')
const FileManagerPage = () => import('@/pages/FileManagerPage.vue')
const PrimaryAgentPage = () => import('@/pages/PrimaryAgentPage.vue')
const StyleLabPage = () => import('@/pages/StyleLabPage.vue')
const SystemSettingsPage = () => import('@/pages/SystemSettingsPage.vue')
const SubagentOverridePage = () => import('@/pages/SubagentOverridePage.vue')
const WorkerProfilePage = () => import('@/pages/WorkerProfilePage.vue')
const TerminologyPage = () => import('@/pages/TerminologyPage.vue')

export interface NavigationItem {
  path: string
  labelKey: string
  icon: string
  sectionPrefix: string
}

export const navigationItems: NavigationItem[] = [
  { path: '/', labelKey: 'navigation.home', icon: 'bi-house', sectionPrefix: '/' },
  { path: '/system/config', labelKey: 'navigation.system', icon: 'bi-gear', sectionPrefix: '/system' },
  { path: '/agents/primary', labelKey: 'navigation.agents', icon: 'bi-robot', sectionPrefix: '/agents' },
  { path: '/components/model', labelKey: 'navigation.components', icon: 'bi-boxes', sectionPrefix: '/components' },
  { path: '/library/model', labelKey: 'navigation.library', icon: 'bi-archive', sectionPrefix: '/library' },
  { path: '/terminology', labelKey: 'navigation.terminology', icon: 'bi-book', sectionPrefix: '/terminology' },
]

export interface SectionNavigationItem {
  path: string
  labelKey: string
}

interface SectionNavigationGroup {
  prefix: string
  items: SectionNavigationItem[]
}

const sectionNavigationGroups: SectionNavigationGroup[] = [
  {
    prefix: '/system',
    items: [
      { path: '/system/config', labelKey: 'navigation.sections.systemSettings' },
      { path: '/system/files', labelKey: 'navigation.sections.fileManager' },
      { path: '/system/events', labelKey: 'navigation.sections.eventFeed' },
      { path: '/system/agent-sessions', labelKey: 'navigation.sections.agentSessions' },
      { path: '/system/style-lab', labelKey: 'navigation.sections.styleLab' },
    ],
  },
  {
    prefix: '/agents',
    items: [
      { path: '/agents/primary', labelKey: 'navigation.sections.primary' },
      { path: '/agents/subagents', labelKey: 'navigation.sections.subagentOverrides' },
      { path: '/agents/workers', labelKey: 'navigation.sections.workerProfiles' },
    ],
  },
]

export function sectionNavigationForPath(path: string): SectionNavigationItem[] {
  return sectionNavigationGroups.find((group) => path.startsWith(group.prefix))?.items ?? []
}

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', component: ApiServerSettingsPage, meta: { titleKey: 'apiServer.homeTitle' } },
    { path: '/agents/primary', component: PrimaryAgentPage, meta: { titleKey: 'navigation.agents' } },
    { path: '/agents/subagents', component: SubagentOverridePage, meta: { titleKey: 'navigation.agents' } },
    { path: '/agents/workers', component: WorkerProfilePage, meta: { titleKey: 'navigation.agents' } },
    { path: '/components/:type', component: ComponentsPage, meta: { titleKey: 'components.title' } },
    { path: '/library/:type', component: ConfigLibraryPage, meta: { titleKey: 'library.title' } },
    {
      path: '/system/config',
      component: SystemSettingsPage,
      meta: { titleKey: 'navigation.system' },
    },
    {
      path: '/system/files',
      component: FileManagerPage,
      meta: { titleKey: 'navigation.system' },
    },
    { path: '/system/events', component: EventFeedPage, meta: { titleKey: 'navigation.system' } },
    { path: '/system/agent-sessions', component: AgentSessionsPage, meta: { titleKey: 'navigation.system' } },
    { path: '/system/style-lab', component: StyleLabPage, meta: { titleKey: 'navigation.system' } },
    {
      path: '/terminology',
      component: TerminologyPage,
      meta: { titleKey: 'terminology.title' },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
