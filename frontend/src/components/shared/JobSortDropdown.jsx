import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { ArrowUpDown } from 'lucide-react';

export function JobSortDropdown({ value, onChange }) {
  return (
    <div className="flex items-center gap-2" data-testid="job-sort-dropdown">
      <ArrowUpDown className="w-4 h-4 text-slate-400" />
      <Select value={value || 'newest'} onValueChange={onChange}>
        <SelectTrigger className="w-[150px] h-9 text-sm">
          <SelectValue placeholder="Sort by" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="newest">Newest First</SelectItem>
          <SelectItem value="oldest">Oldest First</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}
