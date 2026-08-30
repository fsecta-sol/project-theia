"use client";

import { useSyncExternalStore } from "react";

// Client-only gate: server render returns a neutral backdrop, then the real
// tree mounts once the browser is available. useSyncExternalStore avoids the
// setState-in-effect lint error while preserving the same single-mount behavior.
const emptySubscribe = () => () => {};
const getServerSnapshot = () => false;
const getClientSnapshot = () => true;

export default function ClientOnly({ children }: { children: React.ReactNode }) {
  const mounted = useSyncExternalStore(emptySubscribe, getClientSnapshot, getServerSnapshot);

  if (!mounted) {
    return (
      <div suppressHydrationWarning style={{ minHeight: "100vh", background: "oklch(16% 0 0)" }} />
    );
  }

  return children;
}
