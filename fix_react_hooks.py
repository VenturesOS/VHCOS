#!/usr/bin/env python3
"""
Auto-fix React Hook Dependencies
Analyzes useEffect/useCallback hooks and suggests missing dependencies
"""
import re
import sys
from pathlib import Path

def find_hook_issues(file_path):
    """Find useEffect/useCallback hooks with potential missing dependencies"""
    with open(file_path, 'r') as f:
        content = f.read()
    
    issues = []
    
    # Pattern: useEffect(() => { ... }, [deps])
    hook_pattern = r'(useEffect|useCallback|useMemo)\s*\(\s*(?:async\s+)?\(.*?\)\s*=>\s*\{(.*?)\},\s*\[(.*?)\]\s*\)'
    
    for match in re.finditer(hook_pattern, content, re.DOTALL):
        hook_type = match.group(1)
        hook_body = match.group(2)
        deps_str = match.group(3).strip()
        
        # Extract variable references in hook body
        var_refs = set(re.findall(r'\b([a-z][a-zA-Z0-9_]*)\b', hook_body))
        
        # Parse existing dependencies
        existing_deps = set()
        if deps_str:
            existing_deps = set(dep.strip() for dep in deps_str.split(','))
        
        # Filter out common false positives
        exclude = {'const', 'let', 'var', 'return', 'if', 'else', 'for', 'while', 'function', 
                   'true', 'false', 'null', 'undefined', 'console', 'window', 'document',
                   'Math', 'JSON', 'Promise', 'async', 'await'}
        var_refs = var_refs - exclude
        
        # Find potentially missing deps
        potentially_missing = var_refs - existing_deps
        
        if potentially_missing and len(potentially_missing) < 10:  # Avoid false positives
            issues.append({
                'hook': hook_type,
                'line': content[:match.start()].count('\n') + 1,
                'existing_deps': list(existing_deps),
                'potentially_missing': list(potentially_missing)
            })
    
    return issues

if __name__ == '__main__':
    files = [
        '/app/frontend/src/pages/shared/ResumeBuilderPage.jsx',
        '/app/frontend/src/pages/shared/NaukriProfileView.jsx',
        '/app/frontend/src/pages/shared/ActivityFeedPage.jsx',
    ]
    
    for file_path in files:
        if Path(file_path).exists():
            issues = find_hook_issues(file_path)
            if issues:
                print(f"\n📁 {file_path}")
                print(f"Found {len(issues)} potential hook dependency issues\n")
                for issue in issues[:5]:  # Show first 5
                    print(f"  Line {issue['line']}: {issue['hook']}")
                    print(f"    Existing deps: {issue['existing_deps']}")
                    print(f"    Potentially missing: {issue['potentially_missing'][:5]}")
                    print()
