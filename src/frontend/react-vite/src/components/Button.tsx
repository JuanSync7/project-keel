import type { ReactNode } from 'react'

interface ButtonProps {
  readonly children: ReactNode
  readonly onClick: () => void
}

export function Button({ children, onClick }: ButtonProps): React.JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-lg bg-slate-900 px-4 py-2 font-medium text-white transition hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-400"
    >
      {children}
    </button>
  )
}
