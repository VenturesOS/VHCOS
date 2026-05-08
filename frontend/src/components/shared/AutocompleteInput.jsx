import { useState, useRef, useEffect } from 'react';
import { candidateBankAPI } from '../../lib/api';
import { Input } from '../ui/input';

export function AutocompleteInput({ value, onChange, placeholder, field = 'all', className = '', ...props }) {
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const debounceRef = useRef(null);
  const wrapperRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const fetchSuggestions = (q) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!q || q.length < 2) { setSuggestions([]); setShowSuggestions(false); return; }

    // Get the last word/phrase after comma for multi-value inputs
    const lastPart = q.split(',').pop().trim();
    if (lastPart.length < 2) { setSuggestions([]); return; }

    debounceRef.current = setTimeout(async () => {
      try {
        const res = await candidateBankAPI.autocomplete({ q: lastPart, field, limit: 10 });
        setSuggestions(res.data || []);
        setShowSuggestions((res.data || []).length > 0);
        setActiveIndex(-1);
      } catch {
        setSuggestions([]);
      }
    }, 200);
  };

  const handleSelect = (suggestion) => {
    // For comma-separated inputs, append to existing value
    const parts = value.split(',').map(p => p.trim()).filter(Boolean);
    parts.pop(); // Remove partial input
    parts.push(suggestion.text);
    onChange(parts.join(', '));
    setShowSuggestions(false);
  };

  const handleKeyDown = (e) => {
    if (!showSuggestions) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex(i => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex(i => Math.max(i - 1, -1));
    } else if (e.key === 'Enter' && activeIndex >= 0) {
      e.preventDefault();
      handleSelect(suggestions[activeIndex]);
    } else if (e.key === 'Escape') {
      setShowSuggestions(false);
    }
  };

  const TYPE_COLORS = {
    skills: 'bg-green-50 text-green-600',
    designation: 'bg-blue-50 text-blue-600',
    company: 'bg-purple-50 text-purple-600',
    location: 'bg-amber-50 text-amber-600',
    smart_tags: 'bg-indigo-50 text-indigo-600',
    synonym: 'bg-slate-50 text-slate-500 italic',
  };

  return (
    <div ref={wrapperRef} className="relative">
      <Input
        value={value}
        onChange={(e) => { onChange(e.target.value); fetchSuggestions(e.target.value); }}
        onFocus={() => { if (suggestions.length > 0) setShowSuggestions(true); }}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        className={className}
        autoComplete="off"
        {...props}
      />
      {showSuggestions && suggestions.length > 0 && (
        <div className="absolute z-50 w-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-56 overflow-y-auto" data-testid="autocomplete-dropdown">
          {suggestions.map((s, i) => (
            <button
              key={`${s.text}-${s.type}`}
              className={`w-full text-left px-3 py-2 text-sm flex items-center justify-between hover:bg-slate-50 ${i === activeIndex ? 'bg-slate-100' : ''}`}
              onClick={() => handleSelect(s)}
              onMouseEnter={() => setActiveIndex(i)}
            >
              <span className="truncate font-medium text-slate-800">{s.text}</span>
              <div className="flex items-center gap-2 shrink-0 ml-2">
                {s.count > 0 && <span className="text-xs text-slate-400">{s.count}</span>}
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${TYPE_COLORS[s.type] || 'bg-slate-50 text-slate-500'}`}>
                  {s.type}
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
