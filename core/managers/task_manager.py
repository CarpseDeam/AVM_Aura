import asyncio
from typing import Optional, Dict
from PySide6.QtWidgets import QMessageBox

from event_bus import EventBus
from core.managers.service_manager import ServiceManager
from core.managers.window_manager import WindowManager


class TaskManager:
    """
    Manages background task lifecycle and coordination.
    """
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.ai_task: Optional[asyncio.Task] = None
        self.terminal_tasks: Dict[int, asyncio.Task] = {}
        self.service_manager: ServiceManager = None
        self.window_manager: WindowManager = None
        print("[TaskManager] Initialized")

    def set_managers(self, service_manager: ServiceManager, window_manager: WindowManager):
        self.service_manager = service_manager
        self.window_manager = window_manager

    def start_ai_workflow_task(self, workflow_coroutine) -> bool:
        """Start an AI workflow task."""
        if self.ai_task and not self.ai_task.done():
            main_window = self.window_manager.get_main_window() if self.window_manager else None
            QMessageBox.warning(main_window, "AI Busy", "The AI is currently processing another request.")
            return False
        self.ai_task = asyncio.create_task(workflow_coroutine)
        self.ai_task.add_done_callback(self._on_ai_task_done)
        print("[TaskManager] Started AI workflow task")
        return True

    def _on_ai_task_done(self, task: asyncio.Task):
        """Handle AI task completion."""
        try:
            task.result()
        except asyncio.CancelledError:
            print("[TaskManager] AI task was cancelled")
        except Exception as e:
            print(f"[TaskManager] CRITICAL ERROR IN AI TASK: {e}")
            import traceback
            traceback.print_exc()
            main_window = self.window_manager.get_main_window() if self.window_manager else None
            QMessageBox.critical(main_window, "Workflow Error", f"The AI workflow failed unexpectedly.\n\nError: {e}")
        finally:
            self.event_bus.emit("ai_workflow_finished")

    async def cancel_all_tasks(self):
        """Cancel all running tasks and wait for them to complete."""
        tasks_to_cancel = []
        if self.ai_task and not self.ai_task.done():
            self.ai_task.cancel()
            tasks_to_cancel.append(self.ai_task)

        if tasks_to_cancel:
            print(f"[TaskManager] Waiting for {len(tasks_to_cancel)} tasks to cancel...")
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        print("[TaskManager] All tasks cancelled")