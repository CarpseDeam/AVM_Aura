# foundry/actions/testing_actions.py
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from prompts.tester import TESTER_PROMPT
from prompts.master_rules import RAW_CODE_OUTPUT_RULE, TYPE_HINTING_RULE, DOCSTRING_RULE
from foundry.actions.file_system_actions import write_file

if TYPE_CHECKING:
    from core.managers import ProjectManager
    from core.llm_client import LLMClient

logger = logging.getLogger(__name__)


def _robustly_clean_llm_output(content: str) -> str:
    """Cleans markdown and other noise from the LLM's code output."""
    content = content.strip()
    code_block_regex = re.compile(r'```(?:python)?\n(.*?)\n```', re.DOTALL)
    match = code_block_regex.search(content)
    if match:
        return match.group(1).strip()
    return content


async def generate_tests_for_file(path: str, project_manager: "ProjectManager", llm_client: "LLMClient") -> str:
    """
    Reads a source file, uses an LLM to generate pytest tests, and writes the tests to a new file.
    """
    logger.info(f"Generating tests for file: {path}")

    source_path = Path(path)
    if not source_path.is_file():
        return f"Error: Source file not found at '{path}'."

    try:
        source_code_to_test = source_path.read_text(encoding='utf-8')
        filename_to_test = source_path.name
    except Exception as e:
        return f"Error reading source file at '{path}': {e}"

    # Determine the path for the new test file
    test_dir = source_path.parent.parent / "tests"
    if 'app' in source_path.parts: # A heuristic to place tests nicely for common structures
        test_dir = project_manager.active_project_path / "tests"
    test_dir.mkdir(parents=True, exist_ok=True)
    test_filename = f"test_{filename_to_test}"
    test_filepath = test_dir / test_filename

    # Prepare and run the LLM call
    prompt = TESTER_PROMPT.format(
        filename_to_test=str(source_path.relative_to(project_manager.active_project_path)),
        source_code_to_test=source_code_to_test,
        TYPE_HINTING_RULE=TYPE_HINTING_RULE.strip(),
        DOCSTRING_RULE=DOCSTRING_RULE.strip(),
        RAW_CODE_OUTPUT_RULE=RAW_CODE_OUTPUT_RULE.strip()
    )

    provider, model = llm_client.get_model_for_role("tester")
    if not provider or not model:
        return "Error: No model configured for 'tester' role. Cannot generate tests."

    logger.info(f"Asking {provider}/{model} to write tests for {filename_to_test}...")

    raw_test_code = "".join([chunk async for chunk in llm_client.stream_chat(provider, model, prompt, "tester")])
    if "error" in raw_test_code.lower():
        return f"Error during test generation from LLM: {raw_test_code}"

    cleaned_code = _robustly_clean_llm_output(raw_test_code)

    if not cleaned_code:
        return "Error: Test generation resulted in empty code."

    # Write the generated test file
    write_result = write_file(str(test_filepath), cleaned_code)
    if "Error" in write_result:
        return f"Error saving generated test file: {write_result}"

    return f"Successfully generated and wrote tests to '{test_filepath.relative_to(project_manager.active_project_path)}'."