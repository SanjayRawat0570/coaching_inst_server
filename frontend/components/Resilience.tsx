import { Component, useEffect, useState } from "react";

/** Catches a render crash anywhere below it and shows a way back, instead of a
 * blank page. */
export class ErrorBoundary extends Component<{ children: any }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: any) {
    console.error("[ui] page crashed:", error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="min-h-screen grid place-items-center p-6">
        <div className="card p-8 max-w-md text-center">
          <h1 className="text-lg font-bold">Something went wrong on this page</h1>
          <p className="muted text-sm mt-2">Your work on the server is safe. Reload to try again.</p>
          <button className="btn-primary mt-5" onClick={() => window.location.reload()}>Reload</button>
        </div>
      </div>
    );
  }
}

/** A banner while the browser is offline. */
export function OfflineBanner() {
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    const update = () => setOffline(!navigator.onLine);
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  if (!offline) return null;
  return (
    <div role="alert" className="fixed top-0 inset-x-0 z-50 bg-amber-500 text-black text-sm text-center py-1.5 font-medium">
      You're offline. Answers on a test are kept on this device; other actions need a connection.
    </div>
  );
}
