interface NavigationItem {
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
  { path: '/style-lab', labelKey: 'navigation.styleLab', icon: 'bi-sliders', sectionPrefix: '/style-lab' },
]

interface SectionNavigationItem {
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
    ],
  },
  {
    prefix: '/agents',
    items: [
      { path: '/agents/primary', labelKey: 'navigation.sections.primary' },
      { path: '/agents/subagents', labelKey: 'navigation.sections.subagents' },
    ],
  },
]

export function sectionNavigationForPath(path: string): SectionNavigationItem[] {
  return sectionNavigationGroups.find((group) => path.startsWith(group.prefix))?.items ?? []
}
