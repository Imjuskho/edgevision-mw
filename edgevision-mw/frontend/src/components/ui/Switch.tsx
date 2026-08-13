import { cn } from "./cn";

export interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  id?: string;
  disabled?: boolean;
}

export function Switch({ checked, onChange, label, id, disabled }: SwitchProps) {
  return (
    <label className="ui-checkbox" htmlFor={id}>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        className={cn("ui-switch", checked && "ui-switch--checked")}
        onClick={() => onChange(!checked)}
      >
        <span className="ui-switch__thumb" />
      </button>
      {label && <span>{label}</span>}
    </label>
  );
}
