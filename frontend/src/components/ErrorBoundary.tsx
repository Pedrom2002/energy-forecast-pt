import { Component, type ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div className="flex flex-col items-center justify-center min-h-[60vh] animate-fade-in-up">
          <div className="bg-surface border border-border rounded-2xl p-8 sm:p-10 text-center max-w-md shadow-lg">
            <div className="w-16 h-16 rounded-2xl bg-red-50 dark:bg-red-900/20 flex items-center justify-center mx-auto mb-4">
              <AlertTriangle className="w-8 h-8 text-red-500" aria-hidden="true" />
            </div>
            <h1 className="text-xl font-bold text-text-primary">Algo correu mal</h1>
            <p className="text-sm text-text-secondary mt-2">
              Ocorreu um erro inesperado na aplicacao.
            </p>
            {this.state.error && (
              <details className="mt-3 text-left">
                <summary className="text-xs text-text-muted cursor-pointer hover:text-text-secondary">
                  Detalhes do erro
                </summary>
                <pre className="mt-2 text-xs text-red-600 dark:text-red-400 bg-surface-dim rounded-lg p-3 overflow-auto max-h-32 font-mono">
                  {this.state.error.message}
                </pre>
              </details>
            )}
            <button
              type="button"
              onClick={this.handleReset}
              className="mt-6 inline-flex items-center gap-2 text-sm font-medium bg-primary-600 hover:bg-primary-700
                text-white px-5 min-h-[44px] rounded-lg transition-colors shadow-sm cursor-pointer
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2
                active:scale-[0.98]"
            >
              <RefreshCw className="w-4 h-4" aria-hidden="true" />
              Tentar novamente
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
