# gui/controller.py
import logging
import queue
import threading
from typing import Optional, List

from event_bus import EventBus
from events import (
    UserPromptEntered,
    PlanApproved,
    PlanDenied,
    BlueprintInvocation,
    PauseExecutionForUserInput,
    PlanReadyForApproval
)

logger = logging.getLogger(__name__)

class GUIController:
    """
    Handles all the application logic and state management for the GUI.
    The AuraMainWindow is the 'view', and this is the 'controller'.
    """

    def __init__(self, view, event_bus: EventBus):
        self.view = view  # The AuraMainWindow instance
        self.event_bus = event_bus

        # References to the view's widgets that this controller will manage
        self.output_text = view.output_text
        self.input_frame = view.input_frame
        self.approval_frame = view.approval_frame
        self.prompt_entry = view.prompt_entry
        self.submit_button = view.submit_button
        self.auto_approve_switch = view.auto_approve_switch

        # Internal state
        self.ui_queue = queue.Queue()
        self.paused_question: Optional[str] = None
        self.plan_for_approval: Optional[List[BlueprintInvocation]] = None

    def start_ui_loop(self):
        """Starts the recurring queue processing loop."""
        self.view.after(100, self._process_queue)

    def display_message(self, message: str, tag: str):
        """Public method for other threads (like the backend) to queue UI updates."""
        self.ui_queue.put(('MESSAGE', message, tag))

    def _process_queue(self):
        """Processes tasks from the UI queue to update the GUI safely."""
        try:
            while not self.ui_queue.empty():
                task_type, *data = self.ui_queue.get_nowait()
                self.output_text.configure(state="normal")

                if task_type == 'MESSAGE':
                    message, tag = data
                    self._insert_formatted_message(message, tag)

                elif task_type == 'PAUSE':
                    question, = data
                    self.paused_question = question
                    self.output_text.insert("end", f"🤔 Aura Asks:\n{question}\n\n", ("aura_question",))
                    self.prompt_entry.configure(state="normal")
                    self.submit_button.configure(state="normal")
                    self.view._set_placeholder()
                    self.prompt_entry.focus_set()

                elif task_type == 'APPROVAL':
                    plan, = data
                    self.plan_for_approval = plan
                    self.input_frame.grid_remove()  # Hide the normal input

                    plan_text = "Aura's Plan requires your approval:\n"
                    for i, invocation in enumerate(plan):
                        params = ", ".join(f"{k}='{v}'" for k, v in invocation.parameters.items())
                        plan_text += f"  {i+1}. {invocation.blueprint.id}({params})\n"

                    self.output_text.insert("end", plan_text, ("plan_display",))
                    self.approval_frame.grid()  # Show the Approve/Deny buttons

                self.output_text.configure(state="disabled")
                self.output_text.see("end")
        finally:
            self.view.after(100, self._process_queue)

    def _insert_formatted_message(self, message, base_tag):
        """Parses message for code blocks and inserts with syntax highlighting."""
        parts = self.view.code_block_regex.split(message)

        for i, part in enumerate(parts):
            if not part: continue
            is_code = (i % 2 == 1)
            if is_code:
                self.output_text.insert("end", "\n")
                for text, tag in self.view.highlighter.get_tokens(part):
                    self.output_text.insert("end", text, (tag,))
                self.output_text.insert("end", "\n\n")
            else:
                self.output_text.insert("end", part, (base_tag,))

        if not self.view.code_block_regex.search(message):
            self.output_text.insert("end", "\n\n")

    # --- Event Handlers ---
    def handle_pause_for_input(self, event: PauseExecutionForUserInput):
        logger.info(f"GUI received pause event. Question: {event.question}")
        self.ui_queue.put(('PAUSE', event.question))

    def handle_plan_for_approval(self, event: PlanReadyForApproval):
        logger.info(f"GUI received a plan with {len(event.plan)} steps for approval.")
        self.ui_queue.put(('APPROVAL', event.plan))

    def handle_plan_denied(self, event: PlanDenied):
        self.display_message("Plan denied by user.", "system_message")

    # --- UI Action Methods ---
    def cleanup_approval_ui(self):
        """Hides approval buttons and re-enables the main prompt."""
        self.approval_frame.grid_remove()
        self.input_frame.grid()
        self.plan_for_approval = None
        self.prompt_entry.focus_set()

    def approve_plan(self):
        """Publishes the PlanApproved event when the user clicks approve."""
        if not self.plan_for_approval: return
        logger.info("User approved the plan.")
        self.event_bus.publish(PlanApproved(plan=self.plan_for_approval))
        self.cleanup_approval_ui()

    def deny_plan(self):
        """Publishes the PlanDenied event and cleans up the UI."""
        if not self.plan_for_approval: return
        logger.info("User denied the plan.")
        self.event_bus.publish(PlanDenied())
        self.cleanup_approval_ui()

    def submit_prompt(self, event: Optional[object] = None):
        """Handles the logic for submitting a prompt from the user."""
        prompt_text = self.prompt_entry.get("1.0", "end-1c").strip()
        if not prompt_text or "placeholder" in self.prompt_entry.tag_names("1.0") or not self.view.backend_ready.is_set():
            return

        self.prompt_entry.delete("1.0", "end")
        self.prompt_entry.configure(state="disabled")
        self.submit_button.configure(state="disabled")

        is_auto_approved = self.auto_approve_switch.get() == 1
        logger.info(f"Submitting prompt with auto_approve_plan = {is_auto_approved}")

        if self.paused_question:
            self.display_message(f"👤 You (Answer):\n{prompt_text}", "user_prompt")
            final_prompt = (
                f"I previously asked: '{self.paused_question}'. "
                f"The user has now replied: '{prompt_text}'. "
                "Please continue the task based on this new information."
            )
            self.paused_question = None
        else:
            self.display_message(f"👤 You:\n{prompt_text}", "user_prompt")
            final_prompt = prompt_text

        self.view._set_placeholder()
        threading.Thread(target=self._publish_prompt_event, args=(final_prompt, is_auto_approved), daemon=True).start()

    def _publish_prompt_event(self, prompt_text: str, auto_approve: bool):
        """Publishes the final prompt to the event bus."""
        if self.event_bus:
            self.event_bus.publish(UserPromptEntered(prompt_text=prompt_text, auto_approve_plan=auto_approve))
        else:
            self.display_message("ERROR: Event bus not available.", "avm_error")