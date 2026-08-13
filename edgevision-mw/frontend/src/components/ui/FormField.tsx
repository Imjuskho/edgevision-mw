import type { ReactNode } from "react";
import { cn } from "./cn";

export interface FormFieldProps {
  label?: string;
  hint?: string;
  error?: string;
  htmlFor?: string;
  children: ReactNode;
  className?: string;
}

export function FormField({ label, hint, error, htmlFor, children, className }: FormFieldProps) {
  return (
    <div className={cn("ui-input-wrap", className)}>
      {label && (
        <label className="ui-input-label" htmlFor={htmlFor}>
          {label}
        </label>
      )}
      {children}
      {error ? (
        <span className="ui-input-error" role="alert">
          {error}
        </span>
      ) : hint ? (
        <span className="ui-input-hint">{hint}</span>
      ) : null}
    </div>
  );
}
