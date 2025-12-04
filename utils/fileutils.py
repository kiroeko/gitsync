import os
import stat

def make_file_writable(file_path: str) -> None:
    current_permissions = os.stat(file_path).st_mode
    new_permissions = current_permissions | stat.S_IWRITE
    if new_permissions != current_permissions:
        os.chmod(file_path, new_permissions)
        print(f"File permissions changed: {file_path}")

def make_files_writable(directory_path: str) -> None:
    for root, _, files in os.walk(directory_path):
        for file in files:
            file_path = os.path.join(root, file)
            make_file_writable(file_path)

