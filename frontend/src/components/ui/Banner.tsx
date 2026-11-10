import type { ReactNode } from 'react'

type BannerProps = {
  kind?: 'error' | 'success'
  children: ReactNode
}

export function Banner({ kind = 'error', children }: BannerProps) {
  return (
    <div className={`banner banner--${kind}`} role={kind === 'error' ? 'alert' : 'status'}>
      {children}
    </div>
  )
}
