import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Button } from "./Button";
import { cn } from "./cn";

export interface TourStep {
  id: string;
  target?: string;
  title: string;
  body: string;
}

export interface TourProps {
  open: boolean;
  steps: TourStep[];
  stepIndex: number;
  onNext: () => void;
  onPrev: () => void;
  onSkip: () => void;
  onFinish: () => void;
}

export function Tour({ open, steps, stepIndex, onNext, onPrev, onSkip, onFinish }: TourProps) {
  const [rect, setRect] = useState<DOMRect | null>(null);
  const step = steps[stepIndex];
  const isLast = stepIndex >= steps.length - 1;

  useEffect(() => {
    if (!open) return;
    const updateRect = () => {
      if (!step?.target) {
        setRect(null);
        return;
      }
      const el = document.querySelector(step.target);
      setRect(el ? el.getBoundingClientRect() : null);
    };
    updateRect();
    window.addEventListener("resize", updateRect);
    window.addEventListener("scroll", updateRect, true);
    return () => {
      window.removeEventListener("resize", updateRect);
      window.removeEventListener("scroll", updateRect, true);
    };
  }, [open, step?.target]);

  if (!open || !step) return null;

  return createPortal(
    <div className="ui-tour" role="dialog" aria-modal="true" aria-labelledby="ui-tour-title">
      <div className="ui-tour__backdrop" onClick={onSkip} aria-hidden />
      {rect && (
        <div
          className="ui-tour__highlight"
          style={{
            top: rect.top - 4,
            left: rect.left - 4,
            width: rect.width + 8,
            height: rect.height + 8,
          }}
        />
      )}
      <div className={cn("ui-tour__card", !rect && "ui-tour__card--centered")}>
        <p className="ui-tour__step-count">
          {stepIndex + 1} / {steps.length}
        </p>
        <h2 id="ui-tour-title" className="ui-tour__title">
          {step.title}
        </h2>
        <p className="ui-tour__body">{step.body}</p>
        <div className="ui-tour__actions">
          <Button variant="ghost" size="sm" onClick={onSkip}>
            Skip
          </Button>
          <div className="ui-tour__nav">
            <Button variant="secondary" size="sm" onClick={onPrev} disabled={stepIndex === 0}>
              Back
            </Button>
            <Button variant="primary" size="sm" onClick={isLast ? onFinish : onNext}>
              {isLast ? "Done" : "Next"}
            </Button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
