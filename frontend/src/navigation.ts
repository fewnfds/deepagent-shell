interface NavigationItem {
  path: string
  labelKey: string
  icon: string
}

export const navigationItems: NavigationItem[] = [
  { path: '/', labelKey: 'navigation.home', icon: 'bi-house' },
  { path: '/system', labelKey: 'navigation.system', icon: 'bi-gear' },
  { path: '/workflows', labelKey: 'navigation.workflows', icon: 'bi-diagram-3' },
  { path: '/agents', labelKey: 'navigation.agents', icon: 'bi-robot' },
  { path: '/components', labelKey: 'navigation.components', icon: 'bi-boxes' },
  { path: '/library', labelKey: 'navigation.library', icon: 'bi-archive' },
  { path: '/terminology', labelKey: 'navigation.terminology', icon: 'bi-book' },
  { path: '/style-lab', labelKey: 'navigation.styleLab', icon: 'bi-sliders' },
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
    ],
  },
  {
    prefix: '/agents',
    items: [
      { path: '/agents/main', labelKey: 'navigation.sections.mainAgent' },
      { path: '/agents/subagents', labelKey: 'navigation.sections.subagents' },
    ],
  },
]

export function sectionNavigationForPath(path: string): SectionNavigationItem[] {
  return sectionNavigationGroups.find((group) => path.startsWith(group.prefix))?.items ?? []
}
