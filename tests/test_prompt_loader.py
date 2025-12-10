import unittest
from game.utils.prompt_loader import (
    load_prompt,
    get_base_sys_prompt,
    get_op_sys_prompt,
    get_spy_sys_prompt,
    get_rule_sys_prompt,
    clear_prompt_cache,
)


class PromptLoaderTests(unittest.TestCase):
    def setUp(self):
        clear_prompt_cache()

    def test_load_base_prompt(self):
        content = get_base_sys_prompt()
        self.assertIsInstance(content, str)
        self.assertGreater(len(content), 0)

    def test_role_prompts_include_base(self):
        base = get_base_sys_prompt()
        op = get_op_sys_prompt()
        spy = get_spy_sys_prompt()
        rule = get_rule_sys_prompt()

        self.assertIn(base, op)
        self.assertIn(base, spy)
        self.assertIn(base, rule)

    def test_cache_behavior_mtime_invalidation(self):
        # First call populates cache
        original = load_prompt("baseSysPrompt")

        # Modify the file to change mtime and content
        from pathlib import Path

        prompts_dir = Path(__file__).parent.parent / "game" / "data" / "prompts"
        file_path = prompts_dir / "baseSysPrompt.txt"

        backup = file_path.read_text(encoding="utf-8")
        try:
            file_path.write_text(backup + "\nTest marker for mtime.", encoding="utf-8")
            updated = load_prompt("baseSysPrompt")
            self.assertNotEqual(original, updated)
        finally:
            file_path.write_text(backup, encoding="utf-8")

    def test_missing_prompt_raises(self):
        clear_prompt_cache()
        with self.assertRaises(FileNotFoundError):
            load_prompt("nonexistent_prompt_name")


if __name__ == "__main__":
    unittest.main()
