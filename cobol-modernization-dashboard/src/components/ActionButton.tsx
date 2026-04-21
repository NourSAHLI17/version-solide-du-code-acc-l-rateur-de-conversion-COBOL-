"use client";

import { ButtonHTMLAttributes } from "react";

interface ActionButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary";
}

export default function ActionButton({
  children,
  className = "",
  variant = "primary",
  ...props
}: ActionButtonProps) {
  return (
    <button
      {...props}
      className={`action-button ${variant === "secondary" ? "secondary" : "primary"} ${className}`.trim()}
    >
      {children}
    </button>
  );
}
