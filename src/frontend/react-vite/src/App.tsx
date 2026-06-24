import { useState } from 'react'
import { Button } from './components/Button'
import type { Thing } from './types'

export function App(): React.JSX.Element {
  const [thing, setThing] = useState<Thing>({ name: 'hello', value: 0 })

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-3xl font-bold tracking-tight text-slate-900">
        {thing.name}: {thing.value}
      </h1>
      <Button
        onClick={() => {
          setThing((t) => ({ ...t, value: t.value + 1 }))
        }}
      >
        increment
      </Button>
    </main>
  )
}
