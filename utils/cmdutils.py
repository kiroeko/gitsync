import subprocess

def run_cmd(
        cmd: list[str],
        verbose: bool = True
    ) -> tuple[int, str, str]:

    if verbose:
        print("Executing command:", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True, 
        text=True)
    
    if verbose:
        if result.stdout is not None and result.stdout != "":
            print(f"stdout: {result.stdout}")
        if result.stderr is not None and result.stderr != "":
            print(f"stderr: {result.stderr}")

    return (result.returncode, result.stdout, result.stderr)