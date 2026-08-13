import { cn } from "./cn";

export interface BreadcrumbItem {
  label: string;
  href?: string;
  onClick?: () => void;
}

export interface BreadcrumbsProps {
  items: BreadcrumbItem[];
  className?: string;
}

export function Breadcrumbs({ items, className }: BreadcrumbsProps) {
  return (
    <nav className={cn("ui-breadcrumbs", className)} aria-label="Breadcrumb">
      {items.map((item, i) => {
        const isLast = i === items.length - 1;
        return (
          <span key={`${item.label}-${i}`} className="ui-breadcrumbs__segment">
            {i > 0 && (
              <span className="ui-breadcrumbs__sep" aria-hidden>
                /
              </span>
            )}
            {isLast ? (
              <span className="ui-breadcrumbs__current" aria-current="page">
                {item.label}
              </span>
            ) : item.onClick ? (
              <button type="button" className="ui-breadcrumbs__link" onClick={item.onClick}>
                {item.label}
              </button>
            ) : (
              <a className="ui-breadcrumbs__link" href={item.href}>
                {item.label}
              </a>
            )}
          </span>
        );
      })}
    </nav>
  );
}
