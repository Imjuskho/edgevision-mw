import { useEffect, useCallback } from "react";
import { getAllLabelsForContext } from "../utils/annotateLabels";

interface UseAnnotateKeyboardOptions {
  enabled: boolean;
  taxonomyContext: "road" | "agri";
  selectedLabel: string;
  onLabelChange: (label: string) => void;
  onSave: () => void;
  onNext: () => void;
  onPrev: () => void;
  onNextUnlabeled?: () => void;
}

export function useAnnotateKeyboard({
  enabled,
  taxonomyContext,
  onLabelChange,
  onSave,
  onNext,
  onPrev,
  onNextUnlabeled,
}: UseAnnotateKeyboardOptions) {
  const applyClassByIndex = useCallback(
    (index: number) => {
      const labels = getAllLabelsForContext(taxonomyContext);
      const target = labels[index];
      if (target) onLabelChange(target.label);
    },
    [taxonomyContext, onLabelChange],
  );

  useEffect(() => {
    if (!enabled) return;

    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        onSave();
        return;
      }

      if (e.key === "n" || e.key === "N") {
        if (onNextUnlabeled) {
          e.preventDefault();
          onNextUnlabeled();
        } else {
          e.preventDefault();
          onNext();
        }
        return;
      }

      if (e.key === "p" || e.key === "P") {
        e.preventDefault();
        onPrev();
        return;
      }

      if (e.key >= "1" && e.key <= "9") {
        e.preventDefault();
        applyClassByIndex(parseInt(e.key, 10) - 1);
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled, onSave, onNext, onPrev, onNextUnlabeled, applyClassByIndex]);
}
