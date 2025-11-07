import re
import sys
from pathlib import Path

def get_kernel_version(file_path):
    """
    Robustly extracts and returns the Linux kernel version in x.y.z format.
    It finds all printable character sequences in the binary to locate the version string.
    """
    kernel_file = Path(file_path)
    if not kernel_file.exists():
        print(f"Error: Kernel file not found at '{file_path}'", file=sys.stderr)
        return None

    try:
        content = kernel_file.read_bytes()
        potential_strings = re.findall(b'[ -~]{10,}', content)
        
        found_version = None
        for string_bytes in potential_strings:
            try:
                line = string_bytes.decode('ascii', errors='ignore')
                if 'Linux version ' in line:
                    base_version_match = re.search(r'(\d+\.\d+\.\d+)', line)
                    if base_version_match:
                        found_version = base_version_match.group(1)
                        print(f"Full kernel string found: {line.strip()}", file=sys.stderr)
                        break
            except UnicodeDecodeError:
                continue

        if found_version:
            return found_version
        else:
            print("Error: Could not find or parse 'Linux version' string in the kernel file.", file=sys.stderr)
            return None

    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        return None

if __name__ == "__main__":
    path_to_check = 'kernel'
    if len(sys.argv) > 1:
        path_to_check = sys.argv[1]
    
    version = get_kernel_version(path_to_check)
    if version:
        print(version)
    else:
        sys.exit(1)