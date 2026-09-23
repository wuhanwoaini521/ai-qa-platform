import React from 'react';

interface ErrorBoundaryProps {
  children: React.ReactNode;
  /** Changing this value resets the boundary (used to recover on route change). */
  resetKey?: string;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Catches render-time and lifecycle errors below it so a broken page never leaves a blank screen.
 * Data-fetching failures are handled per page with `ErrorState`; this is the last line of defence.
 */
export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidUpdate(prevProps: ErrorBoundaryProps): void {
    if (prevProps.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    console.error('Unhandled UI error', error, info.componentStack);
  }

  render(): React.ReactNode {
    if (this.state.error) {
      return (
        <div style={{ padding: '32px', textAlign: 'center' }}>
          <div style={{ fontWeight: 600, marginBottom: '8px' }}>This view failed to render</div>
          <pre
            style={{
              whiteSpace: 'pre-wrap',
              fontSize: '12px',
              color: 'var(--text-muted)',
              marginBottom: '16px',
            }}
          >
            {this.state.error.message}
          </pre>
          <button type="button" className="btn btn-primary" onClick={() => this.setState({ error: null })}>
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
