"""
Extract ACTUAL LLM prompt commands from backend code.
Shows the complete prompts (system + user) sent to AI APIs.
"""
import os
import re
import ast

def estimate_tokens(text: str) -> int:
    """Rough token estimation: 1 token ≈ 4 characters"""
    return len(text) // 4

def extract_llm_calls(filepath: str):
    """Extract all LLM API calls with their prompts."""
    calls = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Pattern 1: groq_chat_completion calls
        groq_calls = re.findall(
            r'await groq_chat_completion\((.*?)\)',
            content,
            re.DOTALL
        )
        
        # Pattern 2: chat_completion calls (llm_service)
        chat_calls = re.findall(
            r'await chat_completion\((.*?)\)',
            content,
            re.DOTALL
        )
        
        # Pattern 3: _llm_chat calls
        llm_chat_calls = re.findall(
            r'await _llm_chat\((.*?)\)',
            content,
            re.DOTALL
        )
        
        # Pattern 4: _call_claude calls
        claude_calls = re.findall(
            r'await _call_claude\((.*?)\)',
            content,
            re.DOTALL
        )
        
        # Pattern 5: extract_with_fallback calls
        fallback_calls = re.findall(
            r'await extract_with_fallback\((.*?)\)',
            content,
            re.DOTALL
        )
        
        # Pattern 6: LlmChat send_message
        emergent_calls = re.findall(
            r'await chat\.send_message\((.*?)\)',
            content,
            re.DOTALL
        )
        
        all_calls = (
            [(c, 'groq_chat_completion', filepath) for c in groq_calls] +
            [(c, 'chat_completion', filepath) for c in chat_calls] +
            [(c, '_llm_chat', filepath) for c in llm_chat_calls] +
            [(c, '_call_claude', filepath) for c in claude_calls] +
            [(c, 'extract_with_fallback', filepath) for c in fallback_calls] +
            [(c, 'emergent_chat', filepath) for c in emergent_calls]
        )
        
        for call_args, call_type, fpath in all_calls:
            calls.append({
                'file': fpath,
                'call_type': call_type,
                'args_preview': call_args[:300] if len(call_args) < 500 else call_args[:300] + '...',
                'full_args': call_args
            })
            
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
    
    return calls

def find_prompt_definition(content: str, var_name: str) -> str:
    """Find the definition of a prompt variable in the code."""
    # Look for var_name = """...""" or var_name = f"""..."""
    pattern = rf'{var_name}\s*=\s*[fFrR]?"""(.*?)"""'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1)
    
    # Look for var_name = "..." or var_name = f"..."
    pattern = rf'{var_name}\s*=\s*[fFrR]?"(.*?)"'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1)
    
    return None

def analyze_file_for_commands(filepath: str):
    """Extract complete prompt commands from a file."""
    commands = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find all function definitions that call LLM APIs
        functions = re.findall(
            r'(?:async )?def ([a-zA-Z_][a-zA-Z0-9_]*)\([^)]*\):[^:]+?(?=(?:async )?def |class |$)',
            content,
            re.DOTALL
        )
        
        # Look for prompt patterns in the file
        system_prompts = {}
        user_prompts = {}
        
        # Extract all system_prompt definitions
        for match in re.finditer(r'system_prompt\s*=\s*[fFrR]?"""(.*?)"""', content, re.DOTALL):
            # Find which function this belongs to
            pos = match.start()
            func_name = "unknown"
            for func_match in re.finditer(r'(?:async )?def ([a-zA-Z_][a-zA-Z0-9_]*)\(', content):
                if func_match.start() < pos:
                    func_name = func_match.group(1)
            system_prompts[func_name] = match.group(1)
        
        # Extract all user_prompt definitions
        for match in re.finditer(r'user_prompt\s*=\s*[fFrR]?"""(.*?)"""', content, re.DOTALL):
            pos = match.start()
            func_name = "unknown"
            for func_match in re.finditer(r'(?:async )?def ([a-zA-Z_][a-zA-Z0-9_]*)\(', content):
                if func_match.start() < pos:
                    func_name = func_match.group(1)
            user_prompts[func_name] = match.group(1)
        
        # Combine system + user prompts for each function
        all_funcs = set(list(system_prompts.keys()) + list(user_prompts.keys()))
        for func in all_funcs:
            sys = system_prompts.get(func, "")
            user = user_prompts.get(func, "")
            
            if sys or user:
                full_prompt = ""
                if sys:
                    full_prompt += f"SYSTEM:\n{sys}\n\n"
                if user:
                    full_prompt += f"USER:\n{user}"
                
                commands.append({
                    'file': filepath,
                    'function': func,
                    'system_prompt': sys,
                    'user_prompt': user,
                    'full_prompt': full_prompt,
                    'system_tokens': estimate_tokens(sys),
                    'user_tokens': estimate_tokens(user),
                    'total_tokens': estimate_tokens(full_prompt)
                })
        
    except Exception as e:
        print(f"Error analyzing {filepath}: {e}")
    
    return commands

def main():
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
    ]
    
    all_commands = []
    
    for filepath in target_files:
        if os.path.exists(filepath):
            commands = analyze_file_for_commands(filepath)
            all_commands.extend(commands)
    
    # Sort by total tokens
    all_commands.sort(key=lambda x: x['total_tokens'], reverse=True)
    
    print("=" * 120)
    print("ACTUAL LLM PROMPT COMMANDS — COMPLETE TEXT SENT TO AI APIs")
    print("=" * 120)
    print(f"\nTotal prompt commands found: {len(all_commands)}\n")
    
    for idx, cmd in enumerate(all_commands, 1):
        filename = os.path.basename(cmd['file'])
        print(f"\n{'='*120}")
        print(f"COMMAND #{idx} | {filename} → {cmd['function']}()")
        print(f"{'='*120}")
        print(f"TOKENS: System={cmd['system_tokens']}, User={cmd['user_tokens']}, TOTAL={cmd['total_tokens']}")
        print(f"\n{'-'*120}")
        print("SYSTEM PROMPT:")
        print(f"{'-'*120}")
        print(cmd['system_prompt'][:800] if len(cmd['system_prompt']) > 800 else cmd['system_prompt'])
        if len(cmd['system_prompt']) > 800:
            print(f"\n[... truncated, {len(cmd['system_prompt'])} total chars, ~{cmd['system_tokens']} tokens ...]")
        
        print(f"\n{'-'*120}")
        print("USER PROMPT:")
        print(f"{'-'*120}")
        print(cmd['user_prompt'][:800] if len(cmd['user_prompt']) > 800 else cmd['user_prompt'])
        if len(cmd['user_prompt']) > 800:
            print(f"\n[... truncated, {len(cmd['user_prompt'])} total chars, ~{cmd['user_tokens']} tokens ...]")
        
        print("\n")
    
    # Summary table
    print("\n" + "=" * 120)
    print("SUMMARY TABLE — TOKEN CONSUMPTION PER COMMAND")
    print("=" * 120)
    print(f"{'#':<4} {'File':<35} {'Function':<40} {'System':<10} {'User':<10} {'TOTAL':<10}")
    print("-" * 120)
    
    for idx, cmd in enumerate(all_commands, 1):
        filename = os.path.basename(cmd['file'])
        func_name = cmd['function'][:38] if len(cmd['function']) > 38 else cmd['function']
        print(f"{idx:<4} {filename:<35} {func_name:<40} {cmd['system_tokens']:<10} {cmd['user_tokens']:<10} {cmd['total_tokens']:<10}")

if __name__ == "__main__":
    main()
