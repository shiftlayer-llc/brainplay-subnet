import os
from pathlib import Path

def load_prompt(prompt_name: str) -> str:
    """
    Load a prompt from the game/prompts directory.
    
    Args:
        prompt_name: Name of the prompt file (without .txt extension)
        
    Returns:
        The content of the prompt file as a string
    """
    # Get the path to the prompts directory
    current_dir = Path(__file__).parent.parent
    prompts_dir = current_dir / "prompts"
    prompt_file = prompts_dir / f"{prompt_name}.txt"
    
    # Read and return the prompt content
    with open(prompt_file, 'r', encoding='utf-8') as f:
        return f.read()

def get_base_sys_prompt() -> str:
    """Load the base system prompt."""
    return load_prompt("baseSysPrompt")

def get_op_sys_prompt() -> str:
    """Load the operative system prompt (includes base prompt)."""
    base_prompt = get_base_sys_prompt()
    op_specific = load_prompt("opSysPrompt")
    return f"{base_prompt}\n\n{op_specific}"

def get_spy_sys_prompt() -> str:
    """Load the spymaster system prompt (includes base prompt)."""
    base_prompt = get_base_sys_prompt()
    spy_specific = load_prompt("spySysPrompt")
    return f"{base_prompt}\n\n{spy_specific}"

def get_rule_sys_prompt() -> str:
    """Load the rule moderator system prompt (includes base prompt)."""
    base_prompt = get_base_sys_prompt()
    rule_specific = load_prompt("ruleSysPrompt")
    return f"{base_prompt}\n\n{rule_specific}"
