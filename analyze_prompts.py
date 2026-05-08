"""
Token Analysis Script — Identify most token-consuming backend prompts.
Estimates based on character count (rough: 1 token ≈ 4 characters).
"""
import os
import re
import sys

# Rough token estimation: 1 token ≈ 4 characters (OpenAI/Anthropic avg)
def estimate_tokens(text: str) -> int:
    return len(text) // 4

def extract_prompts_from_file(filepath: str) -> list:
    """Extract all system_prompt and user_prompt strings from a Python file."""
    prompts = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Pattern 1: system_prompt = """...""" or system_prompt = "..."
        system_prompts = re.findall(
            r'system_prompt\s*=\s*[fFrR]?"""(.*?)"""|system_prompt\s*=\s*[fFrR]?"(.*?)"',
            content,
            re.DOTALL
        )
        
        # Pattern 2: user_prompt = f"""...""" or user_prompt = "..."
        user_prompts = re.findall(
            r'user_prompt\s*=\s*[fFrR]?"""(.*?)"""|user_prompt\s*=\s*[fFrR]?"(.*?)"',
            content,
            re.DOTALL
        )
        
        # Pattern 3: prompt = """..."""
        generic_prompts = re.findall(
            r'^\s*prompt\s*=\s*[fFrR]?"""(.*?)"""',
            content,
            re.DOTALL | re.MULTILINE
        )
        
        # Pattern 4: system_msg or system_message
        system_msgs = re.findall(
            r'system_msg\s*=\s*[fFrR]?"""(.*?)"""|system_msg\s*=\s*[fFrR]?"(.*?)"|system_message\s*=\s*[fFrR]?"""(.*?)"""',
            content,
            re.DOTALL
        )
        
        # Flatten tuples and count
        for match_tuple in system_prompts:
            for text in match_tuple:
                if text and len(text) > 50:  # Filter noise
                    prompts.append({
                        'file': filepath,
                        'type': 'system_prompt',
                        'text': text[:500],  # First 500 chars for preview
                        'char_count': len(text),
                        'estimated_tokens': estimate_tokens(text)
                    })
        
        for match_tuple in user_prompts:
            for text in match_tuple:
                if text and len(text) > 50:
                    prompts.append({
                        'file': filepath,
                        'type': 'user_prompt',
                        'text': text[:500],
                        'char_count': len(text),
                        'estimated_tokens': estimate_tokens(text)
                    })
        
        for text in generic_prompts:
            if text and len(text) > 50:
                prompts.append({
                    'file': filepath,
                    'type': 'prompt',
                    'text': text[:500],
                    'char_count': len(text),
                    'estimated_tokens': estimate_tokens(text)
                })
        
        for match_tuple in system_msgs:
            for text in match_tuple:
                if text and len(text) > 50:
                    prompts.append({
                        'file': filepath,
                        'type': 'system_msg',
                        'text': text[:500],
                        'char_count': len(text),
                        'estimated_tokens': estimate_tokens(text)
                    })
                    
    except Exception as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)
    
    return prompts


def main():
    # Key files to analyze
    target_files = [
        '/app/backend/services/extension_service.py',
        '/app/backend/services/groq_ai_service.py',
        '/app/backend/services/llm_fallback_service.py',
        '/app/backend/services/batch_enrichment.py',
        '/app/backend/services/matching_engine.py',
        '/app/backend/services/groq_service.py',
        '/app/backend/services/bedrock_service.py',
        '/app/backend/routes/resume.py',
        '/app/backend/routes/cv_upload.py',
        '/app/backend/routes/jobs.py',
    ]
    
    all_prompts = []
    
    for filepath in target_files:
        if os.path.exists(filepath):
            prompts = extract_prompts_from_file(filepath)
            all_prompts.extend(prompts)
    
    # Sort by token count (descending)
    all_prompts.sort(key=lambda x: x['estimated_tokens'], reverse=True)
    
    # Display results
    print("=" * 100)
    print("TOKEN CONSUMPTION ANALYSIS — TOP BACKEND PROMPTS")
    print("=" * 100)
    print(f"\nTotal prompts found: {len(all_prompts)}\n")
    
    print("TOP 15 MOST TOKEN-HEAVY PROMPTS:\n")
    print(f"{'#':<4} {'File':<40} {'Type':<20} {'Tokens':<10} {'Chars':<10}")
    print("-" * 100)
    
    for idx, p in enumerate(all_prompts[:15], 1):
        filename = os.path.basename(p['file'])
        print(f"{idx:<4} {filename:<40} {p['type']:<20} {p['estimated_tokens']:<10} {p['char_count']:<10}")
    
    print("\n" + "=" * 100)
    print("DETAILED BREAKDOWN:\n")
    
    for idx, p in enumerate(all_prompts[:10], 1):
        print(f"\n{'='*80}")
        print(f"#{idx} | {os.path.basename(p['file'])} | {p['type']} | ~{p['estimated_tokens']} tokens")
        print(f"{'='*80}")
        print(f"First 300 chars:\n{p['text'][:300]}...")
        print()
    
    # Aggregate by file
    print("\n" + "=" * 100)
    print("TOKEN CONSUMPTION BY FILE:\n")
    
    file_totals = {}
    for p in all_prompts:
        filename = os.path.basename(p['file'])
        if filename not in file_totals:
            file_totals[filename] = {'count': 0, 'tokens': 0}
        file_totals[filename]['count'] += 1
        file_totals[filename]['tokens'] += p['estimated_tokens']
    
    sorted_files = sorted(file_totals.items(), key=lambda x: x[1]['tokens'], reverse=True)
    
    print(f"{'File':<40} {'Prompt Count':<15} {'Total Tokens':<15}")
    print("-" * 100)
    for filename, data in sorted_files:
        print(f"{filename:<40} {data['count']:<15} {data['tokens']:<15}")
    
    print("\n" + "=" * 100)
    print("SUMMARY & RECOMMENDATIONS\n")
    print("=" * 100)
    
    total_tokens = sum(p['estimated_tokens'] for p in all_prompts)
    print(f"Total estimated tokens across all prompts: ~{total_tokens:,}")
    print(f"\nTop 3 files consuming the most tokens:")
    for idx, (filename, data) in enumerate(sorted_files[:3], 1):
        print(f"  {idx}. {filename} — {data['tokens']:,} tokens across {data['count']} prompts")
    
    print("\n🔥 OPTIMIZATION TARGETS:")
    print("   1. Shorten system prompts (often repeated on every API call)")
    print("   2. Reduce redundant instructions in user prompts")
    print("   3. Cache frequently-used prompts to avoid re-transmission")
    print("   4. Use shorter examples/instructions where possible")
    print("   5. Consider prompt templates with variable injection (less repetition)")


if __name__ == "__main__":
    main()
