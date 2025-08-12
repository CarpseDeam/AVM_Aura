# foundry/actions/testing_actions.py
import logging
import re
import ast
import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from event_bus import EventBus
from events import StreamCodeChunk  # <<< CORRECT IMPORT ADDED HERE
from prompts.tester import TESTER_PROMPT
from prompts.master_rules import RAW_CODE_OUTPUT_RULE, TYPE_HINTING_RULE, DOCSTRING_RULE

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


async def generate_tests_for_file(path: str, project_manager: "ProjectManager", llm_client: "LLMClient", event_bus: EventBus) -> str:
    """
    Reads a source file, uses an LLM to generate pytest tests, and writes the tests to a new file.
    This version streams the output to the code viewer in real-time.
    """
    logger.info(f"Generating and streaming tests for file: {path}")

    source_path = Path(path)
    if not source_path.is_file():
        return f"Error: Source file not found at '{path}'."

    try:
        source_code_to_test = source_path.read_text(encoding='utf-8')
        filename_to_test = source_path.name

        tree = ast.parse(source_code_to_test)
        functions_to_test = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
        functions_to_test_str = ", ".join(functions_to_test) or "No functions found."
        file_tree = "\n".join(sorted(list(project_manager.get_project_files().keys()))) or "The project is currently empty."
    except Exception as e:
        return f"Error reading or parsing source file at '{path}': {e}"

    tests_dir = project_manager.active_project_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    test_filename = f"test_{filename_to_test}"
    test_filepath = tests_dir / test_filename
    relative_test_path = str(test_filepath.relative_to(project_manager.active_project_path))

    prompt = TESTER_PROMPT.format(
        filename_to_test=str(source_path.relative_to(project_manager.active_project_path)),
        source_code_to_test=source_code_to_test,
        file_tree=file_tree,
        functions_to_test=functions_to_test_str,
        TYPE_HINTING_RULE=TYPE_HINTING_RULE.strip(),
        DOCSTRING_RULE=DOCSTRING_RULE.strip(),
        RAW_CODE_OUTPUT_RULE=RAW_CODE_OUTPUT_RULE.strip()
    )

    provider, model = llm_client.get_model_for_role("tester")
    if not provider or not model:
        return "Error: No model configured for 'tester' role. Cannot generate tests."

    logger.info(f"Asking {provider}/{model} to write tests for {filename_to_test} with aggressive grounding...")

    raw_code_accumulator = []
    # Emit a "clear screen" event for the target tab first.
    # *** THE FIX IS HERE: ***
    # Instantiating the dataclass, not sending a raw dict.
    event_bus.emit("stream_code_chunk", StreamCodeChunk(filename=relative_test_path, chunk="", is_first_chunk=True))

    try:
        async for chunk in llm_client.stream_chat(provider, model, prompt, "tester"):
            # *** AND THE FIX IS HERE: ***
            # Instantiating the dataclass for each chunk.
            event_bus.emit("stream_code_chunk", StreamCodeChunk(filename=relative_test_path, chunk=chunk))
            raw_code_accumulator.append(chunk)
            await asyncio.sleep(0.01)

        full_raw_code = "".join(raw_code_accumulator)
        if "error" in full_raw_code.lower():
            return f"Error during test generation from LLM: {full_raw_code}"

        cleaned_code = _robustly_clean_llm_output(full_raw_code)

        if not cleaned_code:
            return "Error: Test generation resulted in empty code."

        test_filepath.write_text(cleaned_code, encoding='utf-8')
        logger.info(f"Successfully wrote tests to {test_filepath}")
        return f"Successfully generated and wrote tests to '{relative_test_path}'."

    except Exception as e:
        error_msg = f"An unexpected error occurred during test generation stream: {e}"
        logger.exception(error_msg)
        return error_msg