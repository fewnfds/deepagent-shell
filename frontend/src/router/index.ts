import { createRouter, createWebHashHistory } from 'vue-router'

const AgentSessionsPage = () => import('@/pages/AgentSessionsPage.vue')
const ApiServerSettingsPage = () => import('@/pages/ApiServerSettingsPage.vue')
const AutomationPage = () => import('@/pages/AutomationPage.vue')
const ComponentsPage = () => import('@/pages/ComponentsPage.vue')
const ConfigLibraryPage = () => import('@/pages/ConfigLibraryPage.vue')
const EventFeedPage = () => import('@/pages/EventFeedPage.vue')
const FileManagerPage = () => import('@/pages/FileManagerPage.vue')
const MainAgentPage = () => import('@/pages/MainAgentPage.vue')
const StyleLabPage = () => import('@/pages/StyleLabPage.vue')
const SystemSettingsPage = () => import('@/pages/SystemSettingsPage.vue')
const SubagentPage = () => import('@/pages/SubagentPage.vue')
const TerminologyPage = () => import('@/pages/TerminologyPage.vue')
const GraphWorkspacePage = () => import('@/pages/GraphWorkspacePage.vue')

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', component: ApiServerSettingsPage, meta: { titleKey: 'apiServer.homeTitle' } },
    { path: '/agents', redirect: '/agents/main' },
    { path: '/agents/main', component: MainAgentPage, meta: { titleKey: 'navigation.agents' } },
    { path: '/agents/subagents', component: SubagentPage, meta: { titleKey: 'navigation.agents' } },
    { path: '/workflows', redirect: '/library/workflows' },
    { path: '/workflows/new', component: GraphWorkspacePage, meta: { titleKey: 'navigation.workflows', layout: 'canvas' } },
    { path: '/workflows/:workflowId', component: GraphWorkspacePage, meta: { titleKey: 'navigation.workflows', layout: 'canvas' } },
    { path: '/components', redirect: '/components/model' },
    { path: '/components/:type', component: ComponentsPage, meta: { titleKey: 'components.title' } },
    { path: '/library', redirect: '/library/model' },
    { path: '/library/automation', component: AutomationPage, meta: { titleKey: 'library.title' } },
    { path: '/library/entry-scripts', component: ConfigLibraryPage, meta: { titleKey: 'library.title' } },
    { path: '/library/workflows', component: ConfigLibraryPage, meta: { titleKey: 'library.title' } },
    { path: '/library/:type', component: ConfigLibraryPage, meta: { titleKey: 'library.title' } },
    { path: '/system', redirect: '/system/config' },
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
    { path: '/style-lab', component: StyleLabPage, meta: { titleKey: 'styleLab.title' } },
    {
      path: '/terminology',
      component: TerminologyPage,
      meta: { titleKey: 'terminology.title' },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
