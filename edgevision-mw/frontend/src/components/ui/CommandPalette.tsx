import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "./cn";
import { Kbd } from "./Kbd";

export interface CommandItem {
  id: string;
  label: string;
  group?: string;
  shortcut?: string;
  onSelect: () => void;
}

export interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  items: CommandItem[];
  placeholder?: string;
}

export function CommandPalette({ open, onClose, items, placeholder }: CommandPaletteProps) {
  const { t } = useTranslation();
  const resolvedPlaceholder = placeholder ?? t("common.searchCommands");
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const [prevOpen, setPrevOpen] = useState(open);
  if (open !== prevOpen) {
    setPrevOpen(open);
    if (!open) {
      setQuery("");
      setActiveIndex(0);
    }
  }

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((item) => item.label.toLowerCase().includes(q));
  }, [items, query]);

  const groups = useMemo(() => {
    const map = new Map<string, CommandItem[]>();
    for (const item of filtered) {
      const g = item.group ?? "Actions";
      if (!map.has(g)) map.set(g, []);
      map.get(g)!.push(item);
    }
    return map;
  }, [filtered]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => Math.max(i - 1, 0));
      }
      if (e.key === "Enter" && filtered[activeIndex]) {
        e.preventDefault();
        filtered[activeIndex].onSelect();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, filtered, activeIndex]);

  if (!open) return null;

  let flatIndex = -1;

  return (
    <div className="ui-command-backdrop" onClick={onClose} role="presentation">
      <div className="ui-command-panel" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Command palette">
        <input
          className="ui-command-input"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActiveIndex(0);
          }}
          placeholder={resolvedPlaceholder}
          autoFocus
          aria-label={resolvedPlaceholder}
        />
        <div className="ui-command-list" role="listbox">
          {filtered.length === 0 && (
            <div className="ui-empty-state ui-command-empty">
              <p className="text-body-sm">No results</p>
            </div>
          )}
          {[...groups.entries()].map(([group, groupItems]) => (
            <div key={group}>
              <div className="ui-command-group-label">{group}</div>
              {groupItems.map((item) => {
                flatIndex += 1;
                const idx = flatIndex;
                return (
                  <button
                    key={item.id}
                    type="button"
                    role="option"
                    aria-selected={idx === activeIndex}
                    className={cn("ui-command-item", idx === activeIndex && "ui-command-item--active")}
                    onMouseEnter={() => setActiveIndex(idx)}
                    onClick={() => {
                      item.onSelect();
                      onClose();
                    }}
                  >
                    <span>{item.label}</span>
                    {item.shortcut && <Kbd>{item.shortcut}</Kbd>}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
