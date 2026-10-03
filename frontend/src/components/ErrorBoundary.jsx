import { Component } from "react";
import { AlertTriangle } from "lucide-react";

// A tab left open across a deploy asks for code-split files the new deploy
// replaced ("Loading chunk 8252 failed"). Reloading fetches the new
// index.html and its files; the timestamp guard stops a reload loop if the
// failure is real (e.g. offline).
const STALE_CHUNK = /Loading (CSS )?chunk [\w-]+ failed|ChunkLoadError|Failed to fetch dynamically imported module|Importing a module script failed/i;
const RELOAD_KEY = "madio_chunk_reload_at";

export function isStaleChunkError(error) {
  return STALE_CHUNK.test(`${error?.name || ""} ${error?.message || error || ""}`);
}

function reloadOnceForNewDeploy() {
  try {
    const last = Number(sessionStorage.getItem(RELOAD_KEY) || 0);
    if (Date.now() - last < 60000) return false;
    sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
  } catch {
    // storage blocked: still worth one reload attempt
  }
  window.location.reload();
  return true;
}

/** Catches uncaught render/lifecycle exceptions from a page so one bad
 * screen degrades to a recoverable panel instead of unmounting the whole
 * app shell (sidebar, topbar and nav stay usable).
 *
 * Must stay a class — React exposes no hook equivalent for
 * componentDidCatch/getDerivedStateFromError. */
export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    if (isStaleChunkError(error) && reloadOnceForNewDeploy()) return;
    // No telemetry sink in this app yet; the console is what a support call
    // will actually ask the user to read back.
    console.error("Screen crashed:", error, info?.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="p-6" data-testid="error-boundary">
        <div className="max-w-lg mx-auto mt-10 rounded-2xl border border-slate-200 bg-white p-6 text-center">
          <AlertTriangle size={28} strokeWidth={1.5} className="mx-auto text-amber-500" />
          <div className="font-heading font-semibold text-[var(--ink)] mt-3">
            This screen hit an unexpected error
          </div>
          <div className="text-sm text-[var(--ink-3)] mt-1">
            The rest of the app is still working — you can switch to another
            screen from the menu, or try loading this one again.
          </div>
          <div className="text-xs font-mono text-[var(--ink-3)] bg-[var(--surface-2)] rounded-lg px-3 py-2 mt-4 break-words text-left">
            {String(error?.message || error)}
          </div>
          <button
            onClick={() => (isStaleChunkError(error) ? window.location.reload() : this.setState({ error: null }))}
            className="btn-primary mt-4 px-4"
            data-testid="error-boundary-retry"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }
}
