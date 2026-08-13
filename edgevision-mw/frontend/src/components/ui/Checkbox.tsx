import { Check } from "lucide-react";
import { cn } from "./cn";

export interface CheckboxProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  id?: string;
  disabled?: boolean;
}

export function Checkbox({ checked, onChange, label, id, disabled }: CheckboxProps) {
  return (
    <label className={cn("ui-checkbox", checked && "ui-checkbox--checked")} htmlFor={id}>
      <button
        id={id}
        type="button"
        role="checkbox"
        aria-checked={checked}
        disabled={disabled}
        className="ui-checkbox__box"
        onClick={() => onChange(!checked)}
      >
        {checked && <Check size={12} />}
      </button>
      {label && <span>{label}</span>}
    </label>
  );
}
