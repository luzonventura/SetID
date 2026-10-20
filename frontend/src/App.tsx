import { useEffect } from 'react'

import { DropOverlay } from './components/DropOverlay'
import { Shell } from './components/Shell'
import { Notice } from './components/ui'
import { useRoute } from './lib/router'
import { Home } from './screens/Home'
import { JobScreen } from './screens/JobScreen'
import { Settings } from './screens/Settings'
import { useJobs } from './state/context'
import { JobsProvider } from './state/jobs'

function GlobalError() {
  const { lastError } = useJobs()
  if (!lastError) return null
  return (
    <div className="mb-8">
      <Notice tone="error">{lastError}</Notice>
    </div>
  )
}

export default function App() {
  const route = useRoute()
  const routeKey = route.name === 'job' ? `job-${route.id}` : route.name
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [routeKey])
  return (
    <JobsProvider>
      <Shell route={route}>
        <GlobalError />
        {route.name === 'home' && <Home />}
        {route.name === 'job' && <JobScreen key={route.id} id={route.id} />}
        {route.name === 'settings' && <Settings />}
      </Shell>
      <DropOverlay />
    </JobsProvider>
  )
}
