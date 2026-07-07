import { Component, type ReactNode } from 'react'

interface State {
  error: Error | null
}

/** Last-resort catch so a render bug shows a calm message, not a white page. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div style={{ padding: '48px 24px', textAlign: 'center', fontFamily: 'inherit' }}>
        <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 8 }}>
          Something broke in the interface.
        </div>
        <div style={{ fontSize: 13.5, color: 'var(--mut)', marginBottom: 16 }}>
          Your screenings are unaffected — reload the page to continue.
        </div>
        <button className="sb-btn" onClick={() => window.location.reload()}>
          Reload
        </button>
      </div>
    )
  }
}
