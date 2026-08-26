"use client";

import { DashboardProvider } from "@/lib/dashboard-context";
import { AppShell } from "./AppShell";

export default function Home() {
  return (
    <DashboardProvider>
      <AppShell />
    </DashboardProvider>
  );
}