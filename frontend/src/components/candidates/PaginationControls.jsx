import { Button } from '../ui/button';
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';

export function PaginationControls({ currentPage, totalPages, totalItems, pageSize, onPageChange }) {
  if (totalPages <= 1) return null;

  const goTo = (p) => { if (p >= 1 && p <= totalPages) onPageChange(p); };

  return (
    <div className="border-t border-slate-100 px-3 sm:px-4 py-3 flex flex-col sm:flex-row items-center justify-between gap-2 bg-slate-50/50">
      <div className="text-xs sm:text-sm text-slate-500" data-testid="pagination-info">
        {((currentPage - 1) * pageSize) + 1}-{Math.min(currentPage * pageSize, totalItems)} of {totalItems}
      </div>
      <div className="flex items-center gap-1" data-testid="pagination-controls">
        <Button variant="outline" size="sm" onClick={() => goTo(1)} disabled={currentPage === 1} className="h-8 w-8 p-0 hidden sm:inline-flex">
          <ChevronsLeft className="h-4 w-4" />
        </Button>
        <Button variant="outline" size="sm" onClick={() => goTo(currentPage - 1)} disabled={currentPage === 1} className="h-8 w-8 p-0">
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <div className="flex items-center gap-1 mx-2">
          {[...Array(Math.min(5, totalPages))].map((_, idx) => {
            let pageNum;
            if (totalPages <= 5) pageNum = idx + 1;
            else if (currentPage <= 3) pageNum = idx + 1;
            else if (currentPage >= totalPages - 2) pageNum = totalPages - 4 + idx;
            else pageNum = currentPage - 2 + idx;
            return (
              <Button
                key={pageNum}
                variant={currentPage === pageNum ? "default" : "outline"}
                size="sm"
                onClick={() => goTo(pageNum)}
                className={`h-8 w-8 p-0 ${currentPage === pageNum ? 'bg-[#7CB342] hover:bg-[#689F38]' : ''}`}
              >
                {pageNum}
              </Button>
            );
          })}
        </div>
        <Button variant="outline" size="sm" onClick={() => goTo(currentPage + 1)} disabled={currentPage === totalPages} className="h-8 w-8 p-0">
          <ChevronRight className="h-4 w-4" />
        </Button>
        <Button variant="outline" size="sm" onClick={() => goTo(totalPages)} disabled={currentPage === totalPages} className="h-8 w-8 p-0">
          <ChevronsRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
