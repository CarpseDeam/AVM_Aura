# tests/test_full_workflow.py
import pytest
import asyncio
import json
from pathlib import Path

from core.application import Application
from events import UserPromptEntered, AIWorkflowFinished

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio


@pytest.fixture
async def test_app(tmp_path: Path, mocker):
    """
    A pytest fixture to set up and tear down a test Application instance.
    - Uses a temporary directory for projects.
    - Mocks out the slow background server launch.
    """
    # Mock the project workspace to use a temporary directory
    mocker.patch('core.managers.project_manager.ProjectManager.workspace_root', tmp_path)

    # Mock the background server launch to avoid real subprocesses
    mocker.patch('core.managers.service_manager.ServiceManager.launch_background_servers', return_value=None)

    # Create and initialize the application
    app = Application(project_root=tmp_path)
    await app.initialize_async()

    # The test will run here
    yield app

    # Teardown: shutdown the app gracefully
    await app.shutdown()


async def mock_llm_stream_chat(*args, **kwargs):
    """
    A mock for the LLMClient's stream_chat method.
    It returns predefined responses based on the prompt content,
    simulating the different agents (Dispatcher, Architect, Coder).
    """
    prompt = kwargs.get("prompt", "")

    # 1. Simulate the Dispatcher deciding to build something new
    if "SPECIALIST AGENTS AVAILABLE" in prompt:
        # The dispatcher thinks, then outputs JSON
        response = '<thought>User wants to create a new script. This is a task for the architect.</thought>{"dispatch_to": "ITERATIVE_ARCHITECT"}'
        yield response
        return

    # 2. Simulate the Architect creating a plan
    if "MODIFICATION DIRECTIVES" in prompt or "ARCHITECTURAL DIRECTIVES" in prompt:
        plan = {
            "thought": "The user wants a simple hello world script. The plan is to create a single file 'hello.py' with the classic print statement.",
            "plan": [
                {
                    "tool_name": "stream_and_write_file",
                    "arguments": {
                        "path": "hello.py",
                        "task_description": "Create a simple Python script that prints 'Hello, World!' to the console."
                    }
                }
            ]
        }
        yield json.dumps(plan)
        return

    # 3. Simulate the Coder generating the code for the file
    if "Create a simple Python script that prints 'Hello, World!'" in prompt:
        code = 'print("Hello, World!")\n'
        yield code
        return

    # Fallback for any unexpected calls
    yield f"UNEXPECTED LLM CALL for prompt: {prompt[:100]}..."


async def test_simple_script_creation(test_app: Application, mocker):
    """
    An end-to-end integration test for creating a simple script.
    It simulates a user prompt and verifies that the correct file is created.
    """
    # --- Setup ---
    # Patch the LLM client to use our mock generator
    mocker.patch('core.llm_client.LLMClient.stream_chat', new=mock_llm_stream_chat)

    # The event bus is central to our test coordination
    event_bus = test_app.event_bus

    # We need an asyncio.Event to signal when the workflow is done
    workflow_finished_event = asyncio.Event()

    def on_workflow_finished(event: AIWorkflowFinished):
        print("TEST: Workflow finished event received!")
        workflow_finished_event.set()

    event_bus.subscribe("ai_workflow_finished", on_workflow_finished)

    # --- Action ---
    # Simulate the user typing a prompt and hitting send
    print("TEST: Emitting user prompt...")
    user_prompt = "create a hello world script"
    event_bus.emit("user_prompt_entered", UserPromptEntered(
        prompt_text=user_prompt,
        conversation_history=[{'role': 'user', 'content': user_prompt}]
    ))

    # --- Verification ---
    # Wait for the workflow to complete, with a timeout
    try:
        await asyncio.wait_for(workflow_finished_event.wait(), timeout=10)
    except asyncio.TimeoutError:
        pytest.fail("The AI workflow did not complete within the timeout period.")

    # Now, check the results.
    # The ProjectManager should have created a new project.
    project_manager = test_app.project_manager
    assert project_manager.active_project_path is not None, "A project should have been created."

    # The final file should exist with the correct content.
    expected_file_path = project_manager.active_project_path / "hello.py"
    print(f"TEST: Checking for file at {expected_file_path}")

    assert expected_file_path.exists(), "The 'hello.py' file was not created."

    content = expected_file_path.read_text()
    assert content == 'print("Hello, World!")\n', "The file content is incorrect."

    print("TEST: Success! File was created with correct content.")