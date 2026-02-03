import subprocess
from .logger import Logger

def run_cmd(
        cmd: list[str],
        verbose: bool = True
    ) -> tuple[int, str, str]:

    if verbose:
        print("Executing command:", " ".join(cmd))
        try:
            Logger.info("Executing command: " + " ".join(cmd))
        except Exception:
            pass

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True)

    if verbose:
        if result.stdout is not None and result.stdout != "":
            print(f"stdout: {result.stdout}")
            try:
                Logger.info(f"stdout: {result.stdout}")
            except Exception:
                pass
        if result.stderr is not None and result.stderr != "":
            print(f"stderr: {result.stderr}")
            try:
                Logger.info(f"stderr: {result.stderr}")
            except Exception:
                pass

    return (result.returncode, result.stdout, result.stderr)