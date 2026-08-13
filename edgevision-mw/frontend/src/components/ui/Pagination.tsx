import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "./cn";
import { IconButton } from "./IconButton";

export interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  className?: string;
}

export function Pagination({ page, totalPages, onPageChange, className }: PaginationProps) {
  return (
    <nav className={cn("ui-pagination", className)} aria-label="Pagination">
      <IconButton
        label="Previous page"
        size="sm"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
      >
        <ChevronLeft size={16} />
      </IconButton>
      <span className="text-body-sm text-caption">
        {page} / {totalPages}
      </span>
      <IconButton
        label="Next page"
        size="sm"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
      >
        <ChevronRight size={16} />
      </IconButton>
    </nav>
  );
}
