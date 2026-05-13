"use client";

import { ReactNode } from "react";

import AppTopNav from "@/components/AppTopNav";

export default function ClientChrome({ children }: { children: ReactNode }) {
  return (
    <>
      <AppTopNav />
      {children}
    </>
  );
}
