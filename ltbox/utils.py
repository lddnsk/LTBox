import os
import platform
import re
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

from ltbox.constants import *

# --- Process Execution ---
def run_command(command, shell=False, check=True, env=None, capture=False):
    env = env or os.environ.copy()
    env['PATH'] = str(TOOLS_DIR) + os.pathsep + str(PLATFORM_TOOLS_DIR) + os.pathsep + env['PATH']

    try:
        process = subprocess.run(
            command, shell=shell, check=check, capture_output=True,
            text=True, encoding='utf-8', errors='ignore', env=env
        )
        if not capture:
            if process.stdout:
                print(process.stdout.strip())
            if process.stderr:
                print(process.stderr.strip(), file=sys.stderr)
        return process
    except FileNotFoundError as e:
        print(f"Error: Command not found - {e.filename}", file=sys.stderr)
        raise
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {' '.join(map(str, command))}", file=sys.stderr)
        print(f"Return code: {e.returncode}", file=sys.stderr)
        if e.stdout:
            print(f"Stdout:\n{e.stdout.strip()}", file=sys.stderr)
        if e.stderr:
            print(f"Stderr:\n{e.stderr.strip()}", file=sys.stderr)
        raise

# --- Platform & Executable Helpers ---
def get_platform_executable(name):
    system = platform.system()
    executables = {
        "Windows": f"{name}.exe",
        "Linux": f"{name}-linux",
        "Darwin": f"{name}-macos"
    }
    exe_name = executables.get(system)
    if not exe_name:
        raise RuntimeError(f"Unsupported operating system: {system}")
    return TOOLS_DIR / exe_name

# --- ADB Device Handling ---
def wait_for_adb():
    print("\n--- WAITING FOR ADB DEVICE ---")
    print("[!] Please enable USB Debugging on your device, connect it via USB.")
    print("[!] A 'Allow USB debugging?' prompt will appear on your device.")
    print("[!] Please check 'Always allow from this computer' and tap 'OK'.")
    try:
        run_command([str(ADB_EXE), "wait-for-device"])
        print("[+] ADB device connected.")
    except Exception as e:
        print(f"[!] Error waiting for ADB device: {e}", file=sys.stderr)
        raise

def get_device_model():
    print("[*] Getting device model via ADB...")
    try:
        result = run_command([str(ADB_EXE), "shell", "getprop", "ro.product.model"], capture=True)
        model = result.stdout.strip()
        if not model:
            print("[!] Could not get device model. Is the device authorized?")
            return None
        print(f"[+] Found device model: {model}")
        return model
    except Exception as e:
        print(f"[!] Error getting device model: {e}", file=sys.stderr)
        print("[!] Please ensure the device is connected and authorized.")
        return None

def reboot_to_edl():
    print("[*] Attempting to reboot device to EDL mode via ADB...")
    try:
        run_command([str(ADB_EXE), "reboot", "edl"])
        print("[+] Reboot command sent. Please wait for the device to enter EDL mode.")
    except Exception as e:
        print(f"[!] Failed to send reboot command: {e}", file=sys.stderr)
        print("[!] Please reboot to EDL manually if it fails.")

# --- EDL Device Handling ---
def check_edl_device(silent=False):
    if not silent:
        print("[*] Checking for Qualcomm EDL (9008) device...")
    try:
        result = subprocess.run(
            ['wmic', 'path', 'Win32_PnPEntity', 'where', "Name like 'Qualcomm%9008%'", 'get', 'Name'],
            capture_output=True, text=True, encoding='utf-8', errors='ignore', shell=True
        )
        if "Qualcomm" in result.stdout and "9008" in result.stdout:
            if not silent:
                print("[+] Qualcomm EDL device found.")
            return True
        else:
            if not silent:
                print("[!] No Qualcomm EDL (9008) device found in Device Manager.")
                print("[!] Please connect your device in EDL mode.")
            return False
    except FileNotFoundError:
        if not silent:
            print("[!] WMIC command not found. Cannot check for EDL device.", file=sys.stderr)
        return False
    except Exception as e:
        if not silent:
            print(f"[!] Error checking for EDL device: {e}", file=sys.stderr)
        return False

def wait_for_edl():
    print("\n--- WAITING FOR EDL DEVICE ---")
    if check_edl_device():
        return
    
    while not check_edl_device(silent=True):
        print("[*] Waiting for Qualcomm EDL (9008) device... (Press Ctrl+C to cancel)")
        try:
            time.sleep(2)
        except KeyboardInterrupt:
            print("\n[!] EDL wait cancelled by user.")
            raise
    print("[+] EDL device connected.")

# --- File/Directory Waiters ---
def wait_for_files(directory, required_files, prompt_message):
    directory.mkdir(exist_ok=True)
    while True:
        all_found = True
        missing = []
        for file in required_files:
            if not (directory / file).exists():
                all_found = False
                missing.append(file)
        
        if all_found:
            return True
        
        if platform.system() == "Windows":
            os.system('cls')
        else:
            os.system('clear')
            
        print("--- WAITING FOR FILES ---")
        print(prompt_message)
        print(f"\nPlease place the following file(s) in the '{directory.name}' folder:")
        for f in missing:
            print(f" - {f}")
        print("\nPress Enter when ready...")
        try:
            input()
        except EOFError:
            sys.exit(1)

def wait_for_directory(directory, prompt_message):
    directory.mkdir(exist_ok=True)
    while True:
        if directory.is_dir() and any(directory.iterdir()):
             return True
        
        if platform.system() == "Windows":
            os.system('cls')
        else:
            os.system('clear')
            
        print("--- WAITING FOR FOLDER ---")
        print(prompt_message)
        print(f"\nPlease copy the entire folder into this directory:")
        print(f" - {directory.name}{os.sep}")
        print("\nThis is typically located at:")
        print(r"   C:\ProgramData\RSA\Download\RomFiles\[Your_Firmware_Folder]")
        print("\nPress Enter when ready...")
        try:
            input()
        except EOFError:
            sys.exit(1)

# --- Dependency Check & Downloaders ---
def check_dependencies():
    print("--- Checking for required files ---")
    dependencies = {
        "Python Environment": PYTHON_EXE,
        "ADB": ADB_EXE,
        "RSA4096 Key": AVB_DIR / "testkey_rsa4096.pem",
        "RSA2048 Key": AVB_DIR / "testkey_rsa2048.pem",
        "avbtool": AVBTOOL_PY,
        "fetch tool": get_platform_executable("fetch")
    }
    missing_deps = [name for name, path in dependencies.items() if not Path(path).exists()]

    if missing_deps:
        for name in missing_deps:
            print(f"[!] Error: Dependency '{name}' is missing.")
        print("Please run one of the main scripts (e.g., root.bat) to install all required files.")
        sys.exit(1)

    print("[+] All dependencies are present.\n")

def _ensure_magiskboot(fetch_exe, magiskboot_exe):
    if magiskboot_exe.exists():
        return True

    print(f"[!] '{magiskboot_exe.name}' not found. Attempting to download...")
    if platform.system() == "Windows":
        arch = platform.machine()
        arch_map = {
            'AMD64': 'x86_64',
            'ARM64': 'arm64',
        }
        target_arch = arch_map.get(arch, 'i686')
        
        asset_pattern = f"magiskboot-.*-windows-.*-{target_arch}-standalone\\.zip"
        
        print(f"[*] Detected Windows architecture: {arch}. Selecting matching magiskboot binary.")
        
        try:
            fetch_command = [
                str(fetch_exe),
                "--repo", MAGISKBOOT_REPO_URL,
                "--tag", MAGISKBOOT_TAG,
                "--release-asset", asset_pattern,
                str(TOOLS_DIR)
            ]
            run_command(fetch_command, capture=True)

            downloaded_zips = list(TOOLS_DIR.glob("magiskboot-*-windows-*.zip"))
            
            if not downloaded_zips:
                raise FileNotFoundError("Failed to find the downloaded magiskboot zip archive.")
            
            downloaded_zip_path = downloaded_zips[0]
            
            with zipfile.ZipFile(downloaded_zip_path, 'r') as zip_ref:
                magiskboot_info = None
                for member in zip_ref.infolist():
                    if member.filename.endswith('magiskboot.exe'):
                        magiskboot_info = member
                        break
                
                if not magiskboot_info:
                    raise FileNotFoundError("magiskboot.exe not found inside the downloaded zip archive.")

                zip_ref.extract(magiskboot_info, path=TOOLS_DIR)
                
                extracted_path = TOOLS_DIR / magiskboot_info.filename
                
                shutil.move(extracted_path, magiskboot_exe)
                
                parent_dir = extracted_path.parent
                if parent_dir.is_dir() and parent_dir != TOOLS_DIR:
                     try:
                        parent_dir.rmdir()
                     except OSError:
                        shutil.rmtree(parent_dir)

            downloaded_zip_path.unlink()
            print("[+] Download and extraction successful.")
            return True

        except (subprocess.CalledProcessError, FileNotFoundError, KeyError, IndexError) as e:
            print(f"[!] Error downloading or extracting magiskboot: {e}", file=sys.stderr)
            sys.exit(1)

    else:
        print(f"[!] Auto-download for {platform.system()} is not supported. Please add it to the 'tools' folder manually.")
        sys.exit(1)

def _get_gki_kernel(fetch_exe, kernel_version, work_dir):
    print("\n[3/8] Downloading GKI Kernel with fetch...")
    asset_pattern = f".*{kernel_version}.*AnyKernel3.zip"
    fetch_command = [
        str(fetch_exe), "--repo", REPO_URL, "--tag", RELEASE_TAG,
        "--release-asset", asset_pattern, str(work_dir)
    ]
    run_command(fetch_command)

    downloaded_files = list(work_dir.glob(f"*{kernel_version}*AnyKernel3.zip"))
    if not downloaded_files:
        print(f"[!] Failed to download AnyKernel3.zip for kernel {kernel_version}.")
        sys.exit(1)
    
    anykernel_zip = work_dir / ANYKERNEL_ZIP_FILENAME
    shutil.move(downloaded_files[0], anykernel_zip)
    print("[+] Download complete.")

    print("\n[4/8] Extracting new kernel image...")
    extracted_kernel_dir = work_dir / "extracted_kernel"
    with zipfile.ZipFile(anykernel_zip, 'r') as zip_ref:
        zip_ref.extractall(extracted_kernel_dir)
    
    kernel_image = extracted_kernel_dir / "Image"
    if not kernel_image.exists():
        print("[!] 'Image' file not found in the downloaded zip.")
        sys.exit(1)
    print("[+] Extraction successful.")
    return kernel_image

def _download_ksu_apk(fetch_exe, target_dir):
    print("\n[7/8] Downloading KernelSU Manager APKs...")
    if list(target_dir.glob("KernelSU*.apk")):
        print("[+] KernelSU Manager APK already exists. Skipping download.")
    else:
        ksu_apk_command = [
            str(fetch_exe), "--repo", f"https://github.com/{KSU_APK_REPO}", "--tag", KSU_APK_TAG,
            "--release-asset", ".*\\.apk", str(target_dir)
        ]
        run_command(ksu_apk_command)
        print("[+] KernelSU Manager APKs downloaded to the main directory (if found).")

def _ensure_edl_ng():
    if platform.system() != "Windows":
        print("[!] EDL functions are only supported on Windows.", file=sys.stderr)
        sys.exit(1)
        
    edl_ng_exe = TOOLS_DIR / "edl-ng.exe"
    if edl_ng_exe.exists():
        return edl_ng_exe

    fetch_exe = get_platform_executable("fetch")
    if not fetch_exe.exists():
         print(f"[!] '{fetch_exe.name}' not found. Please run install.bat")
         sys.exit(1)

    print(f"[!] '{edl_ng_exe.name}' not found. Attempting to download...")
    arch = platform.machine()
    if arch == 'AMD64':
        asset_pattern = "edl-ng-windows-x64.zip"
    elif arch == 'ARM64':
        asset_pattern = "edl-ng-windows-arm64.zip"
    else:
        print(f"[!] Unsupported Windows architecture: {arch}. Cannot download edl-ng.", file=sys.stderr)
        sys.exit(1)
        
    print(f"[*] Detected {arch} architecture. Downloading '{asset_pattern}'...")

    try:
        fetch_command = [
            str(fetch_exe),
            "--repo", EDL_NG_REPO_URL,
            "--tag", EDL_NG_TAG,
            "--release-asset", asset_pattern,
            str(TOOLS_DIR)
        ]
        run_command(fetch_command, capture=True)

        downloaded_zip_path = TOOLS_DIR / asset_pattern
        
        if not downloaded_zip_path.exists():
            raise FileNotFoundError(f"Failed to find the downloaded edl-ng zip archive: {asset_pattern}")
        
        with zipfile.ZipFile(downloaded_zip_path, 'r') as zip_ref:
            edl_info = None
            for member in zip_ref.infolist():
                if member.filename.endswith('edl-ng.exe'):
                    edl_info = member
                    break
            
            if not edl_info:
                raise FileNotFoundError("edl-ng.exe not found inside the downloaded zip archive.")

            zip_ref.extract(edl_info, path=TOOLS_DIR)
            
            extracted_path = TOOLS_DIR / edl_info.filename
            if extracted_path != edl_ng_exe:
                shutil.move(extracted_path, edl_ng_exe)
                parent_dir = extracted_path.parent
                if parent_dir.is_dir() and parent_dir != TOOLS_DIR:
                    try:
                        parent_dir.rmdir()
                    except OSError:
                        shutil.rmtree(parent_dir, ignore_errors=True)

        downloaded_zip_path.unlink()
        print("[+] edl-ng download and extraction successful.")
        return edl_ng_exe

    except (subprocess.CalledProcessError, FileNotFoundError, KeyError, IndexError) as e:
        print(f"[!] Error downloading or extracting edl-ng: {e}", file=sys.stderr)
        sys.exit(1)

# --- AVB (Android Verified Boot) Helpers ---
def extract_image_avb_info(image_path):
    info_proc = run_command(
        [str(PYTHON_EXE), str(AVBTOOL_PY), "info_image", "--image", str(image_path)],
        capture=True
    )
    
    output = info_proc.stdout.strip()
    info = {}
    props_args = []

    partition_size_match = re.search(r"^Image size:\s*(\d+)\s*bytes", output, re.MULTILINE)
    if partition_size_match:
        info['partition_size'] = partition_size_match.group(1)
    
    data_size_match = re.search(r"Original image size:\s*(\d+)\s*bytes", output)
    if data_size_match:
        info['data_size'] = data_size_match.group(1)
    else:
        desc_size_match = re.search(r"^\s*Image Size:\s*(\d+)\s*bytes", output, re.MULTILINE)
        if desc_size_match:
            info['data_size'] = desc_size_match.group(1)

    patterns = {
        'name': r"Partition Name:\s*(\S+)",
        'salt': r"Salt:\s*([0-9a-fA-F]+)",
        'algorithm': r"Algorithm:\s*(\S+)",
        'pubkey_sha1': r"Public key \(sha1\):\s*([0-9a-fA-F]+)",
    }
    
    header_section = output.split('Descriptors:')[0]
    rollback_match = re.search(r"Rollback Index:\s*(\d+)", header_section)
    if rollback_match:
        info['rollback'] = rollback_match.group(1)
        
    flags_match = re.search(r"Flags:\s*(\d+)", header_section)
    if flags_match:
        info['flags'] = flags_match.group(1)
        if output: 
            print(f"[Info] Parsed Flags: {info['flags']}")
        
    for key, pattern in patterns.items():
        if key not in info:
            match = re.search(pattern, output)
            if match:
                info[key] = match.group(1)

    for line in output.split('\n'):
        if line.strip().startswith("Prop:"):
            parts = line.split('->')
            key = parts[0].split(':')[-1].strip()
            val = parts[1].strip()[1:-1]
            info[key] = val
            props_args.extend(["--prop", f"{key}:{val}"])
            
    info['props_args'] = props_args
    if props_args and output: 
        print(f"[Info] Parsed {len(props_args) // 2} properties.")

    return info

def _apply_hash_footer(image_path, image_info, key_file, new_rollback_index=None):
    rollback_index = new_rollback_index if new_rollback_index is not None else image_info['rollback']
    
    print(f"\n[*] Adding hash footer to '{image_path.name}'...")
    print(f"  > Partition: {image_info['name']}, Rollback Index: {rollback_index}")

    add_footer_cmd = [
        str(PYTHON_EXE), str(AVBTOOL_PY), "add_hash_footer",
        "--image", str(image_path), 
        "--key", str(key_file),
        "--algorithm", image_info['algorithm'], 
        "--partition_size", image_info['partition_size'],
        "--partition_name", image_info['name'], 
        "--rollback_index", str(rollback_index),
        "--salt", image_info['salt'], 
        *image_info.get('props_args', [])
    ]
    
    if 'flags' in image_info:
        add_footer_cmd.extend(["--flags", image_info.get('flags', '0')])
        print(f"  > Restoring flags: {image_info.get('flags', '0')}")

    run_command(add_footer_cmd)
    print(f"[+] Successfully applied hash footer to {image_path.name}.")

def patch_chained_image_rollback(image_name, current_rb_index, new_image_path, patched_image_path):
    try:
        print(f"[*] Analyzing new {image_name}...")
        info = extract_image_avb_info(new_image_path)
        new_rb_index = int(info.get('rollback', '0'))
        print(f"  > New index: {new_rb_index}")

        if new_rb_index >= current_rb_index:
            print(f"[*] {image_name} index is OK. Copying as is.")
            shutil.copy(new_image_path, patched_image_path)
            return

        print(f"[!] Anti-Rollback Bypassed: Patching {image_name} from {new_rb_index} to {current_rb_index}...")
        
        for key in ['partition_size', 'name', 'salt', 'algorithm', 'pubkey_sha1']:
            if key not in info:
                raise KeyError(f"Could not find '{key}' in '{new_image_path.name}' AVB info.")
        
        key_file = KEY_MAP.get(info['pubkey_sha1']) 
        if not key_file:
            raise KeyError(f"Unknown public key SHA1 {info['pubkey_sha1']} in {new_image_path.name}")
        
        shutil.copy(new_image_path, patched_image_path)
        
        _apply_hash_footer(
            image_path=patched_image_path,
            image_info=info,
            key_file=key_file,
            new_rollback_index=str(current_rb_index)
        )

    except (KeyError, subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[!] Error processing {image_name}: {e}", file=sys.stderr)
        raise

def patch_vbmeta_image_rollback(image_name, current_rb_index, new_image_path, patched_image_path):
    try:
        print(f"[*] Analyzing new {image_name}...")
        info = extract_image_avb_info(new_image_path)
        new_rb_index = int(info.get('rollback', '0'))
        print(f"  > New index: {new_rb_index}")

        if new_rb_index >= current_rb_index:
            print(f"[*] {image_name} index is OK. Copying as is.")
            shutil.copy(new_image_path, patched_image_path)
            return

        print(f"[!] Anti-Rollback Bypassed: Patching {image_name} from {new_rb_index} to {current_rb_index}...")

        for key in ['algorithm', 'pubkey_sha1']:
            if key not in info:
                raise KeyError(f"Could not find '{key}' in '{new_image_path.name}' AVB info.")
        
        key_file = KEY_MAP.get(info['pubkey_sha1']) 
        if not key_file:
            raise KeyError(f"Unknown public key SHA1 {info['pubkey_sha1']} in {new_image_path.name}")

        remake_cmd = [
            str(PYTHON_EXE), str(AVBTOOL_PY), "make_vbmeta_image",
            "--output", str(patched_image_path),
            "--key", str(key_file),
            "--algorithm", info['algorithm'],
            "--rollback_index", str(current_rb_index),
            "--flags", info.get('flags', '0'),
            "--include_descriptors_from_image", str(new_image_path)
        ]
        
        run_command(remake_cmd)
        print(f"[+] Successfully patched {image_name}.")

    except (KeyError, subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[!] Error processing {image_name}: {e}", file=sys.stderr)
        raise

def process_boot_image(image_to_process):
    print("\n[*] Verifying boot image key and metadata...") 
    boot_bak_img = BASE_DIR / "boot.bak.img"
    if not boot_bak_img.exists():
        print(f"[!] Backup file '{boot_bak_img.name}' not found. Cannot process image.", file=sys.stderr)
        raise FileNotFoundError(f"{boot_bak_img.name} not found.")
        
    boot_info = extract_image_avb_info(boot_bak_img)
    
    for key in ['partition_size', 'name', 'rollback', 'salt', 'algorithm', 'pubkey_sha1']:
        if key not in boot_info:
            raise KeyError(f"Could not find '{key}' in '{boot_bak_img.name}' AVB info.")
            
    boot_pubkey = boot_info.get('pubkey_sha1')
    key_file = KEY_MAP.get(boot_pubkey) 
    
    if not key_file:
        print(f"[!] Public key SHA1 '{boot_pubkey}' from boot.img did not match known keys. Cannot add footer.")
        raise KeyError(f"Unknown boot public key: {boot_pubkey}")

    print(f"[+] Matched {key_file.name}.")
    
    _apply_hash_footer(
        image_path=image_to_process,
        image_info=boot_info,
        key_file=key_file
    )

# --- Info Display ---
def show_image_info(files):
    all_files = []
    for f in files:
        path = Path(f)
        if path.is_dir():
            all_files.extend(path.rglob('*.img'))
        elif path.is_file():
            all_files.append(path)

    if not all_files:
        print("No .img files found in the provided paths.")
        return
        
    output_lines = [
        "\n" + "=" * 42,
        "  Sorted and Processing Images...",
        "=" * 42 + "\n"
    ]
    print("\n".join(output_lines))

    for file_path in sorted(all_files):
        info_header = f"Processing file: {file_path}\n---------------------------------" 
        print(info_header)
        output_lines.append(info_header)

        if not file_path.exists():
            not_found_msg = f"File not found: {file_path}"
            print(not_found_msg)
            output_lines.append(not_found_msg)
            continue

        try:
            process = run_command(
                [str(PYTHON_EXE), str(AVBTOOL_PY), "info_image", "--image", str(file_path)],
            )
            output_lines.append(process.stdout.strip())
        except (subprocess.CalledProcessError) as e:
            error_message = f"Failed to get info from {file_path.name}"
            print(error_message, file=sys.stderr)
            if e.stderr:
                print(e.stderr.strip(), file=sys.stderr)
            output_lines.append(error_message)
        finally:
            output_lines.append("---------------------------------\n")

    try:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        output_filename = BASE_DIR / f"image_info_{timestamp}.txt"
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(output_lines))
        print(f"[*] Image info saved to: {output_filename}")
    except IOError as e:
        print(f"[!] Error saving info to file: {e}", file=sys.stderr)