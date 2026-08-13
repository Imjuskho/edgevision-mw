import type { ReactNode } from "react";
import { AlertCircle } from "lucide-react";
import { cn } from "./cn";
import { Button } from "./Button";

export interface ErrorStateProps {
  title: string;
  body?: string;
  onRetry?: () => void;
  retryLabel?: string;
  action?: ReactNode;
  className?: string;
}

export function ErrorState({ title, body, onRetry, retryLabel = "Retry", action, className }: ErrorStateProps) {
  return (
    <div className={cn("ui-error-state", className)} role="alert">
      <AlertCircle size={32} className="ui-empty-state__icon" />
      <h3 className="ui-empty-state__title">{title}</h3>
      {body && <p className="ui-empty-state__body">{body}</p>}
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          {retryLabel}
        </Button>
      )}
      {action}
    </div>
  );
}
