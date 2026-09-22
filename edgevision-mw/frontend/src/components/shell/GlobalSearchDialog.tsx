import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Database, Image, Server, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CommandItem } from "../ui/CommandPalette";
import { Kbd } from "../ui/Kbd";
import { cn } from "../ui/cn";
import type { GlobalSearchResult } from "../../hooks/useGlobalSearch";

export interface GlobalSearchDialogProps {
  open: boolean;
  onClose: () => void;
  query: string;
  onQueryChange: (q: string) => void;
  results: GlobalSearchResult[];
  loading?: boolean;
  commands: CommandItem[];
  onSelectResult: (result: GlobalSearchResult) => void;
}

const KIND_ICON: Record<GlobalSearchResult["kind"], ReactNode> = {
  dataset: <Database size={16} aria-hidden />,
  node: <Server size={16} aria-hidden />,
  image: <Image size={16} aria-hidden />,
  action: null,
};

export function GlobalSearchDialog({
  open,
  onClose,
  query,
  onQueryChange,
  results,
  loading,
  commands,
  onSelectResult,
}: GlobalSearchDialogProps) {
  const { t } = useTranslation();
  const [activeIndex, setActiveIndex] = useState(0);

  const [prevOpen, setPrevOpen] = useState(open);
  if (open !== prevOpen) {
    setPrevOpen(open);
    if (!open) setActiveIndex(0);
  }

  const filteredCommands = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) => c.label.toLowerCase().includes(q));
  }, [commands, query]);

  const listKey = `${query}|${results.length}|${filteredCommands.length}`;
  const [prevListKey, setPrevListKey] = useState(listKey);
  if (listKey !== prevListKey) {
    setPrevListKey(listKey);
    setActiveIndex(0);
  }

  const flatItems = useMemo(
    () => [
      ...results.map((r) => ({ type: "result" as const, result: r })),
      ...filteredCommands.map((c) => ({ type: "command" as const, command: c })),
    ],
    [results, filteredCommands],
  );

  useEffect(() => {
    if (!open) {
      onQueryChange("");
    }
  }, [open, onQueryChange]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, flatItems.length - 1));
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => Math.max(i - 1, 0));
      }
      if (e.key === "Enter" && flatItems[activeIndex]) {
        e.preventDefault();
        const item = flatItems[activeIndex];
        if (item.type === "result") {
          onSelectResult(item.result);
        } else {
          item.command.onSelect();
        }
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, flatItems, activeIndex, onSelectResult]);

  if (!open) return null;

  const hasQuery = query.trim().length > 0;

  return (
    <div className="ui-command-backdrop" onClick={onClose} role="presentation">
      <div
        className="ui-command-panel"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={t("app.search", "Search")}
      >
        <input
          className="ui-command-input"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder={t("app.searchPlaceholder", "Search datasets, nodes, images, actions…")}
          autoFocus
          aria-label={t("app.search", "Search")}
        />
        <div className="ui-command-list">
          {loading && (
            <div className="ui-command-item ui-command-item--center">
              <Loader2 size={16} aria-hidden className="ui-spin-icon" />
              {t("app.searching", "Searching…")}
            </div>
          )}

          {hasQuery && results.length > 0 && (
            <>
              <div className="ui-command-group-label">{t("app.searchResults", "Results")}</div>
              {results.map((result, i) => {
                const idx = i;
                return (
                  <button
                    key={`${result.kind}-${result.id}`}
                    type="button"
                    className={cn("ui-command-item", idx === activeIndex && "ui-command-item--active")}
                    onMouseEnter={() => setActiveIndex(idx)}
                    onClick={() => {
                      onSelectResult(result);
                      onClose();
                    }}
                  >
                    <span className="ui-command-item-icon">
                      {KIND_ICON[result.kind]}
                      <span>
                        <strong>{result.title}</strong>
                        {result.subtitle && (
                          <span className="text-caption ui-command-subtitle">
                            {result.subtitle}
                          </span>
                        )}
                      </span>
                    </span>
                    {result.meta && <span className="text-caption">{result.meta}</span>}
                  </button>
                );
              })}
            </>
          )}

          {hasQuery && !loading && results.length === 0 && (
            <div className="ui-empty-state ui-command-empty">
              <p className="text-body-sm">{t("app.searchNoResults", "No matches found")}</p>
            </div>
          )}

          <div className="ui-command-group-label">
            {hasQuery ? t("app.searchActions", "Actions") : t("app.searchQuick", "Quick actions")}
          </div>
          {filteredCommands.map((cmd, j) => {
            const idx = results.length + j;
            return (
              <button
                key={cmd.id}
                type="button"
                className={cn("ui-command-item", idx === activeIndex && "ui-command-item--active")}
                onMouseEnter={() => setActiveIndex(idx)}
                onClick={() => {
                  cmd.onSelect();
                  onClose();
                }}
              >
                <span>{cmd.label}</span>
                {cmd.shortcut && <Kbd>{cmd.shortcut}</Kbd>}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
