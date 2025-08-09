import sys
from pathlib import Path

from utils.exception_handler import setup_exception_hook

if getattr(sys, 'frozen', False):
    project_root = Path(sys.executable).parent
else:
    project_root = Path(__file__).parent.resolve()

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import asyncio
import qasync
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon

from core.application import Application



async def main_async_logic(app_instance, root_path: Path):
    """
    The main asynchronous coroutine for the application.
    """
    aura_app = None
    shutdown_future = asyncio.get_event_loop().create_future()
    shutdown_in_progress = False

    async def start_shutdown():
        nonlocal shutdown_in_progress
        if shutdown_in_progress: return
        shutdown_in_progress = True
        print("[main] Shutdown requested. Starting graceful shutdown...")
        if aura_app:
            await aura_app.shutdown()
        if not shutdown_future.done(): shutdown_future.set_result(True)
        print("[main] Graceful shutdown complete.")

    try:
        aura_app = Application(project_root=root_path)
        aura_app.event_bus.subscribe("application_shutdown", lambda: asyncio.create_task(start_shutdown()))

        await aura_app.initialize_async()
        if aura_app.is_fully_initialized():
            aura_app.show()
            print("[main] Application ready and displayed.")
            await shutdown_future
        else:
            print("[main] Application did not initialize fully. Shutting down.", file=sys.stderr)
            raise RuntimeError("Application failed to initialize.")

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
        print("[main] Main async logic has finished. Quitting application.")
        QTimer.singleShot(100, app_instance.quit)


if __name__ == "__main__":
    setup_exception_hook()
    app = QApplication(sys.argv)

    # We take manual control of when the application quits.
    # The main window closing will emit a signal, but not kill the app.
    # Our shutdown logic will call app.quit() when it's done.
    app.setQuitOnLastWindowClosed(False)

    app.setApplicationName("Aura")
    app.setOrganizationName("Aura")

    icon_path = project_root / "assets" / "Ava_Icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
        print(f"[main] Application icon set from: {icon_path}")
    else:
        print(f"[main] WARNING: Application icon not found at {icon_path}")

    qasync.run(main_async_logic(app, project_root))
    print("[main] Application has exited cleanly.")