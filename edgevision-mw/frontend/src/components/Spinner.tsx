export function Spinner({ size = 24, color = "var(--accent-blue)" }: { size?: number; color?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className="ui-spinner"
    >
      <circle
        cx="12"
        cy="12"
        r="10"
        stroke={color}
        strokeWidth="3"
        opacity="0.2"
      />
      <path
        d="M12 2a10 10 0 019.95 9"
        stroke={color}
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function LoadingOverlay({ message }: { message?: string }) {
  return (
    <div className="ui-loading-overlay">
      <Spinner size={36} />
      {message && <span className="ui-loading-overlay__message">{message}</span>}
    </div>
  );
}
