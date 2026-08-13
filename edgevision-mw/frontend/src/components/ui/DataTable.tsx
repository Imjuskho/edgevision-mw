import type { ReactNode } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { cn } from "./cn";
import { EmptyState } from "./EmptyState";
import { SkeletonTable } from "./Skeleton";
import { Spinner } from "./Spinner";

export interface DataTableColumn<T> {
  key: string;
  header: string;
  sortable?: boolean;
  render: (row: T) => ReactNode;
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  data: T[];
  rowKey: (row: T) => string;
  sortKey?: string;
  sortDir?: "asc" | "desc";
  onSort?: (key: string) => void;
  onRowClick?: (row: T) => void;
  loading?: boolean;
  emptyTitle?: string;
  emptyBody?: string;
  className?: string;
  stickyHeader?: boolean;
}

export function DataTable<T>({
  columns,
  data,
  rowKey,
  sortKey,
  sortDir,
  onSort,
  onRowClick,
  loading,
  emptyTitle = "No data",
  emptyBody,
  className,
  stickyHeader,
}: DataTableProps<T>) {
  if (loading) {
    return <SkeletonTable />;
  }

  if (data.length === 0) {
    return <EmptyState title={emptyTitle} body={emptyBody} />;
  }

  return (
    <div className={cn("ui-table-wrap", stickyHeader && "ui-table-wrap--sticky", className)}>
      <table className="ui-table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} scope="col">
                {col.sortable && onSort ? (
                  <button type="button" className="ui-table__sort-btn" onClick={() => onSort(col.key)}>
                    {col.header}
                    {sortKey === col.key &&
                      (sortDir === "asc" ? <ArrowUp size={14} /> : <ArrowDown size={14} />)}
                  </button>
                ) : (
                  col.header
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr
              key={rowKey(row)}
              className={onRowClick ? "ui-table__row--clickable" : undefined}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((col) => (
                <td key={col.key}>{col.render(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function LoadingOverlay({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="ui-loading-overlay ui-loading-overlay--absolute" role="status">
      <Spinner />
      <span className="text-body-sm">{label}</span>
    </div>
  );
}
