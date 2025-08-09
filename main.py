import sys
from pathlib import Path

# --- ROBUST PATH HANDLING ---
# This ensures that the application can find its modules and resources
# regardless of where it's run from.
if getattr(sys, 'frozen', False):
    # Running in a bundled environment (e.g., PyInstaller)
    project_root = Path(sys.executable).parent
    # For bundled apps, the main package 'aura' is at the root.
    sys.path.insert(0, str(project_root))
else:
    # Running from source
    project_root = Path(__file__).parent.resolve()
    # Add the project root to sys.path to allow imports like `from aura.core...`
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

import asyncio
import qasync
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon

# Now it's safe to import from our application's package
from aura.core.application import Application
from aura.utils.exception_handler import setup_exception_hook


async def main_async_logic(app_instance, root_path: Path):
    """
    The main asynchronous coroutine for the application.
    """
    aura_app = None
    shutdown_future = asyncio.get_event_loop().create_future()
    shutdown_in_progress = False

    async def on_about_to_quit():
        nonlocal shutdown_in_progress
        if shutdown_in_progress: return
        shutdown_in_progress = True
        print("[main] Application is about to quit. Starting graceful shutdown...")
        if aura_app:
            try:
                if hasattr(aura_app, 'service_manager') and aura_app.service_manager:
                    await aura_app.service_manager.shutdown()
            except Exception as e:
                print(f"[main] Error during shutdown tasks: {e}")
        if not shutdown_future.done(): shutdown_future.set_result(True)
        print("[main] Graceful shutdown complete.")

    app_instance.aboutToQuit.connect(lambda: asyncio.create_task(on_about_to_quit()))

    try:
        aura_app = Application(project_root=root_path)
        await aura_app.initialize_async()
        aura_app.show()
        print("[main] Application ready and displayed.")
        await shutdown_future
    except Exception as e:
        print(f"[main] CRITICAL ERROR during application startup: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "Startup Error", f"Failed to start Aura.\n\nError: {e}")
        except Exception as msg_e:
            print(f"Could not show error message box: {msg_e}", file=sys.stderr)
    finally:
        print("[main] Main async logic has finished. Exiting.")
        QTimer.singleShot(100, app_instance.quit)


if __name__ == "__main__":
    setup_exception_hook()
    app = QApplication(sys.argv)

    app.setApplicationName("Aura")
    app.setOrganizationName("Aura")

    icon_path = project_root / "aura" / "assets" / "Ava_Icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
        print(f"[main] Application icon set from: {icon_path}")
    else:
        print(f"[main] WARNING: Application icon not found at {icon_path}")

    qasync.run(main_async_logic(app, project_root))
    print("[main] Application has exited cleanly.")