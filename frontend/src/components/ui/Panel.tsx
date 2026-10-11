import type { ReactNode } from 'react'

/** The one card style used across the app. */
export function Panel({ title, icon, actions, children, className = '', id }: {
  title?: ReactNode; icon?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; id?: string
}) {
  return (
    <section className={`panel ${className}`} aria-labelledby={id && title ? `${id}-h` : undefined}>
      {(title || actions) && (
        <header className="panel-head">
          {title && <h2 id={id ? `${id}-h` : undefined}>{icon && <span className="panel-icon" aria-hidden="true">{icon}</span>}{title}</h2>}
          {actions && <div className="panel-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  )
}
