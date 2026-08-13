import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { cn } from "./cn";

export interface SearchInputProps {
  value?: string;
  onChange: (value: string) => void;
  placeholder?: string;
  debounceMs?: number;
  className?: string;
  "aria-label"?: string;
}

export function SearchInput({
  value: controlledValue,
  onChange,
  placeholder = "Search…",
  debounceMs = 300,
  className,
  "aria-label": ariaLabel = "Search",
}: SearchInputProps) {
  const [local, setLocal] = useState(controlledValue ?? "");

  useEffect(() => {
    if (controlledValue !== undefined) setLocal(controlledValue);
  }, [controlledValue]);

  useEffect(() => {
    const timer = window.setTimeout(() => onChange(local), debounceMs);
    return () => window.clearTimeout(timer);
  }, [local, debounceMs, onChange]);

  return (
    <div className={cn("ui-search", className)}>
      <Search size={16} className="ui-search__icon" aria-hidden />
      <input
        type="search"
        className={cn("ui-input", "ui-search__input")}
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel}
      />
    </div>
  );
}
