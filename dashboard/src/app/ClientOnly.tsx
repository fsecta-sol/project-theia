"use client";

import { useState, useEffect } from "react";

export default function ClientOnly({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <div suppressHydrationWarning style={{ minHeight: "100vh", background: "oklch(16% 0 0)" }} />
    );
  }

  return children;
}