import { useEffect, useRef, useCallback } from 'react';

interface ShortcutOptions {
  capture?: boolean;
  preventDefault?: boolean;
  stopPropagation?: boolean;
  enabled?: boolean;
  target?: HTMLElement | Window | null;
}

export function useKeyboardShortcuts(
  handler: (key: string, event: KeyboardEvent) => void,
  options: ShortcutOptions = {}
) {
  const {
    capture = false,
    preventDefault = true,
    enabled = true,
    target = typeof window !== 'undefined' ? window : null,
  } = options;

  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (!enabled) return;

    const targetEl = e.target as HTMLElement;
    if (
      targetEl.tagName === 'INPUT' ||
      targetEl.tagName === 'TEXTAREA' ||
      targetEl.isContentEditable
    ) {
      return;
    }

    const modifiers: string[] = [];
    if (e.ctrlKey || e.metaKey) modifiers.push('Ctrl');
    if (e.altKey) modifiers.push('Alt');
    if (e.shiftKey) modifiers.push('Shift');

    const key = modifiers.length > 0
      ? `${modifiers.join('+')}+${e.key}`
      : e.key;

    handlerRef.current(key, e);

    if (preventDefault) {
      const navigationKeys = [
        'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
        'Space', 'Enter', 'Tab',
      ];
      if (navigationKeys.includes(e.key)) {
        e.preventDefault();
      }
    }
  }, [enabled, preventDefault]);

  useEffect(() => {
    if (!target) return;
    target.addEventListener('keydown', handleKeyDown as EventListener, capture);
    return () => {
      target.removeEventListener('keydown', handleKeyDown as EventListener, capture);
    };
  }, [target, capture, handleKeyDown]);
}

export function useShortcut(
  key: string,
  callback: () => void,
  options: ShortcutOptions = {}
) {
  useKeyboardShortcuts(
    (pressedKey) => {
      if (pressedKey === key) {
        callback();
      }
    },
    options
  );
}
