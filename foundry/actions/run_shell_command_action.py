
import subprocess

def run_shell_command(command):
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return f"Stdout:\n{result.stdout}\nStderr:\n{result.stderr}"
    except subprocess.CalledProcessError as e:
        return f"Error executing command: {e}\nStdout:\n{e.stdout}\nStderr:\n{e.stderr}"
