import { useEffect, useCallback, useRef } from "react";

type KeyHandler = (e: KeyboardEvent) => void;

interface ShortcutMap {
  [key: string]: KeyHandler;
}

export function useKeyboardShortcuts(shortcuts: ShortcutMap) {
  const shortcutsRef = useRef(shortcuts);

  useEffect(() => {
    shortcutsRef.current = shortcuts;
  }, [shortcuts]);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    const target = e.target as HTMLElement;
    if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT") return;

    const key = [
      e.ctrlKey || e.metaKey ? "ctrl" : "",
      e.shiftKey ? "shift" : "",
      e.altKey ? "alt" : "",
      e.key.toLowerCase(),
    ].filter(Boolean).join("+");

    const handler = shortcutsRef.current[key] || shortcutsRef.current[e.key.toLowerCase()];
    if (handler) {
      e.preventDefault();
      handler(e);
    }
  }, []);

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);
}

export function ShortcutHint({ keys }: { keys: string[] }) {
  return (
    <span className="shortcut-hint">
      {keys.map((key) => (
        <kbd key={key} className="shortcut-kbd">
          {key}
        </kbd>
      ))}
    </span>
  );
}
