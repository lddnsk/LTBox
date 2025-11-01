import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import requests

# --- Constants ---
BASE_DIR = Path(__file__).parent.resolve()
TOOLS_DIR = BASE_DIR / "tools"
PYTHON_DIR = BASE_DIR / "python3"
AVB_DIR = TOOLS_DIR / "avb"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_ROOT_DIR = BASE_DIR / "output_root"
OUTPUT_DP_DIR = BASE_DIR / "output_dp"
BACKUP_DIR = BASE_DIR / "backup"
WORK_DIR = BASE_DIR / "patch_work"
INPUT_CURRENT_DIR = BASE_DIR / "input_current"
INPUT_NEW_DIR = BASE_DIR / "input_new"
OUTPUT_ANTI_ROLLBACK_DIR = BASE_DIR / "output_anti_rollback"


PYTHON_EXE = PYTHON_DIR / "python.exe"
AVBTOOL_PY = AVB_DIR / "avbtool.py"
EDIT_IMAGES_PY = TOOLS_DIR / "edit_images.py"
GET_KERNEL_VER_PY = TOOLS_DIR / "get_kernel_ver.py"

MAGISKBOOT_REPO_URL = "https://github.com/PinNaCode/magiskboot_build"
MAGISKBOOT_TAG = "last-ci"

KSU_APK_REPO = "KernelSU-Next/KernelSU-Next"
KSU_APK_TAG = "v1.1.1"

RELEASE_OWNER = "WildKernels"
RELEASE_REPO = "GKI_KernelSU_SUSFS"
RELEASE_TAG = "v1.5.9-r36"
REPO_URL = f"https://github.com/{RELEASE_OWNER}/{RELEASE_REPO}"

ANYKERNEL_ZIP_FILENAME = "AnyKernel3.zip"

EDL_NG_REPO_URL = "https://github.com/strongtz/edl-ng"
EDL_NG_TAG = "v1.4.1"
EDL_LOADER_FILE = BASE_DIR / "xbl_s_devprg_ns.melf"


# --- Helper Functions ---
def run_command(command, shell=False, check=True, env=None, capture=False):
    """Executes a command and handles its output."""
    env = env or os.environ.copy()
    env['PATH'] = str(TOOLS_DIR) + os.pathsep + env['PATH']

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

def check_edl_device():
    print("[*] Checking for Qualcomm EDL (9008) device...")
    try:
        result = subprocess.run(
            ['wmic', 'path', 'Win32_PnPEntity', 'where', "Name like 'Qualcomm%9008%'", 'get', 'Name'],
            capture_output=True, text=True, encoding='utf-8', errors='ignore', shell=True
        )
        if "Qualcomm" in result.stdout and "9008" in result.stdout:
            print("[+] Qualcomm EDL device found.")
            return True
        else:
            print("[!] No Qualcomm EDL (9008) device found in Device Manager.")
            print("[!] Please connect your device in EDL mode.")
            return False
    except FileNotFoundError:
        print("[!] WMIC command not found. Cannot check for EDL device.", file=sys.stderr)
        print("[!] Assuming device is connected. The script will proceed.")
        return True
    except Exception as e:
        print(f"[!] Error checking for EDL device: {e}", file=sys.stderr)
        return False

def get_platform_executable(name):
    """Returns the path to a platform-specific executable."""
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

def check_dependencies():
    """Checks for required files and exits if any are missing."""
    print("--- Checking for required files ---")
    dependencies = {
        "Python Environment": PYTHON_EXE,
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

def extract_image_avb_info(image_path):
    """Extracts AVB metadata from an image file using regex for robustness."""
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
    if props_args:
        print(f"[Info] Parsed {len(props_args) // 2} properties.")

    return info

def wait_for_files(directory, required_files, prompt_message):
    """Waits for user to place files in a directory."""
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


# --- Core Functions ---
def patch_boot_with_root():
    """Patches boot.img with KernelSU and returns the path to the patched image."""
    print("--- Starting boot.img patching process ---")
    magiskboot_exe = get_platform_executable("magiskboot")
    fetch_exe = get_platform_executable("fetch")
    
    patched_boot_path = BASE_DIR / "boot.root.img"

    if not magiskboot_exe.exists():
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

            except (subprocess.CalledProcessError, FileNotFoundError, KeyError, IndexError) as e:
                print(f"[!] Error downloading or extracting magiskboot: {e}", file=sys.stderr)
                sys.exit(1)

        else:
            print(f"[!] Auto-download for {platform.system()} is not supported. Please add it to the 'tools' folder manually.")
            sys.exit(1)

    if not fetch_exe.exists():
         print(f"[!] '{fetch_exe.name}' not found. Please run install.bat")
         sys.exit(1)

    if platform.system() != "Windows":
        os.chmod(magiskboot_exe, 0o755)
        os.chmod(fetch_exe, 0o755)

    boot_img = BASE_DIR / "boot.img"
    if not boot_img.exists():
        print("[!] 'boot.img' not found! Aborting.")
        sys.exit(1)

    shutil.copy(boot_img, BASE_DIR / "boot.bak.img")
    print("--- Backing up original boot.img ---")

    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    WORK_DIR.mkdir()

    original_cwd = Path.cwd()
    os.chdir(WORK_DIR)

    try:
        shutil.copy(boot_img, WORK_DIR)

        print("\n[1/8] Unpacking boot image...")
        run_command([str(magiskboot_exe), "unpack", "boot.img"])
        if not (WORK_DIR / "kernel").exists():
            print("[!] Failed to unpack boot.img. The image might be invalid.")
            sys.exit(1)
        print("[+] Unpack successful.")

        print("\n[2/8] Verifying kernel version...")
        result = run_command([str(PYTHON_EXE), str(GET_KERNEL_VER_PY), "kernel"])
        target_kernel_version = result.stdout.strip()

        if not re.match(r"\d+\.\d+\.\d+", target_kernel_version):
             print(f"[!] Invalid kernel version returned from script: '{target_kernel_version}'")
             sys.exit(1)
        
        print(f"[+] Target kernel version for download: {target_kernel_version}")

        print("\n[3/8] Downloading GKI Kernel with fetch...")
        asset_pattern = f".*{target_kernel_version}.*AnyKernel3.zip"
        fetch_command = [
            str(fetch_exe), "--repo", REPO_URL, "--tag", RELEASE_TAG,
            "--release-asset", asset_pattern, "."
        ]
        run_command(fetch_command)

        downloaded_files = list(Path(".").glob(f"*{target_kernel_version}*AnyKernel3.zip"))
        if not downloaded_files:
            print(f"[!] Failed to download AnyKernel3.zip for kernel {target_kernel_version}.")
            sys.exit(1)
        shutil.move(downloaded_files[0], ANYKERNEL_ZIP_FILENAME)
        print("[+] Download complete.")

        print("\n[4/8] Extracting new kernel image...")
        extracted_kernel_dir = WORK_DIR / "extracted_kernel"
        with zipfile.ZipFile(ANYKERNEL_ZIP_FILENAME, 'r') as zip_ref:
            zip_ref.extractall(extracted_kernel_dir)
        if not (extracted_kernel_dir / "Image").exists():
            print("[!] 'Image' file not found in the downloaded zip.")
            sys.exit(1)
        print("[+] Extraction successful.")

        print("\n[5/8] Replacing original kernel with the new one...")
        shutil.move(str(extracted_kernel_dir / "Image"), "kernel")
        print("[+] Kernel replaced.")

        print("\n[6/8] Repacking boot image...")
        run_command([str(magiskboot_exe), "repack", "boot.img"])
        if not (WORK_DIR / "new-boot.img").exists():
            print("[!] Failed to repack the boot image.")
            sys.exit(1)
        shutil.move("new-boot.img", patched_boot_path)
        print("[+] Repack successful.")

        print("\n[7/8] Downloading KernelSU Manager APKs...")
        if list(BASE_DIR.glob("KernelSU*.apk")):
            print("[+] KernelSU Manager APK already exists. Skipping download.")
        else:
            ksu_apk_command = [
                str(fetch_exe), "--repo", f"https://github.com/{KSU_APK_REPO}", "--tag", KSU_APK_TAG,
                "--release-asset", ".*\\.apk", str(BASE_DIR)
            ]
            run_command(ksu_apk_command)
            print("[+] KernelSU Manager APKs downloaded to the main directory (if found).")

    finally:
        os.chdir(original_cwd)
        if WORK_DIR.exists():
            shutil.rmtree(WORK_DIR)
        if boot_img.exists():
            boot_img.unlink()
        print("\n--- Cleaning up ---")

    if patched_boot_path.exists():
        return patched_boot_path
    return None

def convert_images():
    """Converts vendor_boot and remakes vbmeta, without rooting."""
    check_dependencies()

    print("[*] Cleaning up old folders...")
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    print()

    print("--- Backing up original images ---")
    vendor_boot_img = BASE_DIR / "vendor_boot.img"
    vbmeta_img = BASE_DIR / "vbmeta.img"
    required_images = {"vendor_boot.img": vendor_boot_img, "vbmeta.img": vbmeta_img}

    for name, path in required_images.items():
        if not path.exists():
            print(f"[!] '{name}' not found! Aborting.")
            sys.exit(1)

    vendor_boot_bak = BASE_DIR / "vendor_boot.bak.img"
    vbmeta_bak = BASE_DIR / "vbmeta.bak.img"
    shutil.move(vendor_boot_img, vendor_boot_bak)
    shutil.copy(vbmeta_img, vbmeta_bak)
    print("[+] Backup complete.\n")

    print("--- Starting PRC/ROW Conversion ---")
    run_command([str(PYTHON_EXE), str(EDIT_IMAGES_PY), "vndrboot", str(vendor_boot_bak)])

    vendor_boot_prc = BASE_DIR / "vendor_boot_prc.img"
    print("\n[*] Verifying conversion result...")
    if not vendor_boot_prc.exists():
        print("[!] 'vendor_boot_prc.img' was not created. No changes made.")
        sys.exit(1)
    print("[+] Conversion to PRC successful.\n")

    print("--- Extracting image information ---")
    vbmeta_info = extract_image_avb_info(vbmeta_bak)
    vendor_boot_info = extract_image_avb_info(vendor_boot_bak)
    print("[+] Information extracted.\n")

    print("--- Adding Hash Footer to vendor_boot ---")
    
    for key in ['partition_size', 'name', 'rollback', 'salt']:
        if key not in vendor_boot_info:
            raise KeyError(f"Could not find '{key}' in '{vendor_boot_bak.name}' AVB info.")

    add_hash_footer_cmd = [
        str(PYTHON_EXE), str(AVBTOOL_PY), "add_hash_footer",
        "--image", str(vendor_boot_prc),
        "--partition_size", vendor_boot_info['partition_size'],
        "--partition_name", vendor_boot_info['name'],
        "--rollback_index", vendor_boot_info['rollback'],
        "--salt", vendor_boot_info['salt']
    ]
    
    if 'props_args' in vendor_boot_info:
        add_hash_footer_cmd.extend(vendor_boot_info['props_args'])
        print(f"[+] Restoring {len(vendor_boot_info['props_args']) // 2} properties for vendor_boot.")

    if 'flags' in vendor_boot_info:
        add_hash_footer_cmd.extend(["--flags", vendor_boot_info.get('flags', '0')])
        print(f"[+] Restoring flags for vendor_boot: {vendor_boot_info.get('flags', '0')}")

    run_command(add_hash_footer_cmd)
    
    key_map = {
        "2597c218aae470a130f61162feaae70afd97f011": AVB_DIR / "testkey_rsa4096.pem",
        "cdbb77177f731920bbe0a0f94f84d9038ae0617d": AVB_DIR / "testkey_rsa2048.pem"
    }
    
    vbmeta_pubkey = vbmeta_info.get('pubkey_sha1')
    key_file = key_map.get(vbmeta_pubkey)

    print(f"--- Remaking vbmeta.img ---")
    print("[*] Verifying vbmeta key...")
    if not key_file:
        print(f"[!] Public key SHA1 '{vbmeta_pubkey}' from vbmeta did not match known keys. Aborting.")
        sys.exit(1)
    print(f"[+] Matched {key_file.name}.\n")

    print("[*] Remaking 'vbmeta.img' using descriptors from backup...")
    remake_cmd = [
        str(PYTHON_EXE), str(AVBTOOL_PY), "make_vbmeta_image",
        "--output", str(vbmeta_img),
        "--key", str(key_file),
        "--algorithm", vbmeta_info['algorithm'],
        "--padding_size", "8192",
        "--flags", vbmeta_info.get('flags', '0'),
        "--rollback_index", vbmeta_info.get('rollback', '0'),
        "--include_descriptors_from_image", str(vbmeta_bak),
        "--include_descriptors_from_image", str(vendor_boot_prc)
    ]
        
    run_command(remake_cmd)
    print()

    finalize_images()

def finalize_images():
    """Finalizes the process by moving images to their final destinations."""
    print("--- Finalizing ---")
    print("[*] Renaming final images...")
    final_vendor_boot = BASE_DIR / "vendor_boot.img"
    shutil.move(BASE_DIR / "vendor_boot_prc.img", final_vendor_boot)

    final_images = [final_vendor_boot, BASE_DIR / "vbmeta.img"]

    print("\n[*] Moving final images to 'output' folder...")
    OUTPUT_DIR.mkdir(exist_ok=True)
    for img in final_images:
        shutil.move(img, OUTPUT_DIR / img.name)

    print("\n[*] Moving backup files to 'backup' folder...")
    BACKUP_DIR.mkdir(exist_ok=True)
    for bak_file in BASE_DIR.glob("*.bak.img"):
        shutil.move(bak_file, BACKUP_DIR / bak_file.name)
    print()

    print("=" * 61)
    print("  SUCCESS!")
    print("  Final images have been saved to the 'output' folder.")
    print("=" * 61)
    
def root_boot_only():
    """Patches boot.img with KernelSU and places it in the output_root folder."""
    print(f"[*] Cleaning up old '{OUTPUT_ROOT_DIR.name}' folder...")
    if OUTPUT_ROOT_DIR.exists():
        shutil.rmtree(OUTPUT_ROOT_DIR)
    OUTPUT_ROOT_DIR.mkdir(exist_ok=True)
    print()
    
    check_dependencies()

    patched_boot_path = patch_boot_with_root()

    if patched_boot_path and patched_boot_path.exists():
        print("\n--- Finalizing ---")
        final_boot_img = OUTPUT_ROOT_DIR / "boot.img"
        
        print("\n[*] Verifying boot image key...")
        key_map = {
            "2597c218aae470a130f61162feaae70afd97f011": AVB_DIR / "testkey_rsa4096.pem",
            "cdbb77177f731920bbe0a0f94f84d9038ae0617d": AVB_DIR / "testkey_rsa2048.pem"
        }
        process_boot_image(key_map, patched_boot_path)

        print(f"\n[*] Moving final image to '{OUTPUT_ROOT_DIR.name}' folder...")
        shutil.move(patched_boot_path, final_boot_img)

        print("\n[*] Moving backup file to 'backup' folder...")
        BACKUP_DIR.mkdir(exist_ok=True)
        for bak_file in BASE_DIR.glob("boot.bak.img"):
            shutil.move(bak_file, BACKUP_DIR / bak_file.name)
        print()

        print("=" * 61)
        print("  SUCCESS!")
        print(f"  Patched boot.img has been saved to the '{OUTPUT_ROOT_DIR.name}' folder.")
        print("=" * 61)
    else:
        print("[!] Patched boot image was not created. An error occurred during the process.", file=sys.stderr)


def process_boot_image(key_map, image_to_process):
    """Adds a hash footer to a boot image."""
    boot_bak_img = BASE_DIR / "boot.bak.img"
    boot_info = extract_image_avb_info(boot_bak_img)
    
    for key in ['partition_size', 'name', 'rollback', 'salt', 'algorithm', 'pubkey_sha1']:
        if key not in boot_info:
            raise KeyError(f"Could not find '{key}' in '{boot_bak_img.name}' AVB info.")
            
    boot_pubkey = boot_info.get('pubkey_sha1')
    key_file = key_map.get(boot_pubkey)
    
    if not key_file:
        print(f"[!] Public key SHA1 '{boot_pubkey}' from boot.img did not match known keys. Cannot add footer.")
        sys.exit(1)

    print(f"[+] Matched {key_file.name}.")
    print(f"\n[*] Adding new hash footer to '{image_to_process.name}'...")
    add_footer_cmd = [
        str(PYTHON_EXE), str(AVBTOOL_PY), "add_hash_footer",
        "--image", str(image_to_process), 
        "--key", str(key_file),
        "--algorithm", boot_info['algorithm'], 
        "--partition_size", boot_info['partition_size'],
        "--partition_name", boot_info['name'], 
        "--rollback_index", boot_info['rollback'],
        "--salt", boot_info['salt'], 
        *boot_info.get('props_args', [])
    ]
    
    if 'flags' in boot_info:
        add_footer_cmd.extend(["--flags", boot_info.get('flags', '0')])
        print(f"[+] Restoring flags for boot: {boot_info.get('flags', '0')}")

    run_command(add_footer_cmd)


def edit_devinfo_persist():
    """Backs up and modifies devinfo.img and persist.img."""
    print("--- Starting devinfo & persist patching process ---")
    
    devinfo_img = BASE_DIR / "devinfo.img"
    persist_img = BASE_DIR / "persist.img"
    
    if not devinfo_img.exists() and not persist_img.exists():
        print("[!] Error: 'devinfo.img' and 'persist.img' both not found. Please place at least one in the main directory.")
        sys.exit(1)
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_critical_dir = BASE_DIR / f"backup_critical_{timestamp}"
    backup_critical_dir.mkdir(exist_ok=True)
    
    print(f"[*] Backing up critical images to '{backup_critical_dir.name}'...")
    
    if devinfo_img.exists():
        shutil.copy(devinfo_img, backup_critical_dir)
        print(f"[+] Backed up '{devinfo_img.name}'.")
    if persist_img.exists():
        shutil.copy(persist_img, backup_critical_dir)
        print(f"[+] Backed up '{persist_img.name}'.")
    print("[+] Backup complete.\n")

    print(f"[*] Cleaning up old '{OUTPUT_DP_DIR.name}' folder...")
    if OUTPUT_DP_DIR.exists():
        shutil.rmtree(OUTPUT_DP_DIR)
    OUTPUT_DP_DIR.mkdir(exist_ok=True)

    print("[*] Running patch script...")
    run_command([str(PYTHON_EXE), str(EDIT_IMAGES_PY), "dp"])

    modified_devinfo = BASE_DIR / "devinfo_modified.img"
    modified_persist = BASE_DIR / "persist_modified.img"
    
    if modified_devinfo.exists():
        shutil.move(modified_devinfo, OUTPUT_DP_DIR / "devinfo.img")
    if modified_persist.exists():
        shutil.move(modified_persist, OUTPUT_DP_DIR / "persist.img")
        
    print(f"\n[*] Final images have been moved to '{OUTPUT_DP_DIR.name}' folder.")
    
    print("[*] Cleaning up original image files...")
    devinfo_img.unlink(missing_ok=True)
    persist_img.unlink(missing_ok=True)
    
    print("\n" + "=" * 61)
    print("  SUCCESS!")
    print(f"  Modified images are ready in the '{OUTPUT_DP_DIR.name}' folder.")
    print("=" * 61)


def read_edl():
    print("--- Starting EDL Read Process ---")
    
    if platform.system() != "Windows":
        print("[!] This function is only supported on Windows.", file=sys.stderr)
        sys.exit(1)

    fetch_exe = get_platform_executable("fetch")
    edl_ng_exe = TOOLS_DIR / "edl-ng.exe"

    if not edl_ng_exe.exists():
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

        except (subprocess.CalledProcessError, FileNotFoundError, KeyError, IndexError) as e:
            print(f"[!] Error downloading or extracting edl-ng: {e}", file=sys.stderr)
            sys.exit(1)

    if not EDL_LOADER_FILE.exists():
        print(f"[!] Error: Loader file '{EDL_LOADER_FILE.name}' not found in the main directory.")
        print("[!] Aborting.")
        sys.exit(1)
    print(f"[+] Loader file '{EDL_LOADER_FILE.name}' found.")

    if not check_edl_device():
        sys.exit(1)
        
    print("\n[*] Attempting to read 'devinfo' partition...")
    try:
        run_command([
            str(edl_ng_exe),
            "--loader", str(EDL_LOADER_FILE),
            "read-part", "devinfo", "devinfo.img"
        ])
        print("[+] Successfully read 'devinfo' to devinfo.img.")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[!] Failed to read 'devinfo': {e}", file=sys.stderr)

    print("\n[*] Attempting to read 'persist' partition...")
    try:
        run_command([
            str(edl_ng_exe),
            "--loader", str(EDL_LOADER_FILE),
            "read-part", "persist", "persist.img"
        ])
        print("[+] Successfully read 'persist' to persist.img.")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[!] Failed to read 'persist': {e}", file=sys.stderr)

    print("\n--- EDL Read Process Finished ---")


def write_edl():
    print("--- Starting EDL Write Process ---")

    if platform.system() != "Windows":
        print("[!] This function is only supported on Windows.", file=sys.stderr)
        sys.exit(1)

    if not OUTPUT_DP_DIR.exists():
        print(f"[!] Error: Patched images folder '{OUTPUT_DP_DIR.name}' not found.", file=sys.stderr)
        print("[!] Please run 'devinfo_persist.bat' first to generate the modified images.", file=sys.stderr)
        sys.exit(1)
    print(f"[+] Found patched images folder: '{OUTPUT_DP_DIR.name}'.")

    if not EDL_LOADER_FILE.exists():
        print(f"[!] Error: Loader file '{EDL_LOADER_FILE.name}' not found in the main directory.", file=sys.stderr)
        print("[!] Aborting.")
        sys.exit(1)
    print(f"[+] Loader file '{EDL_LOADER_FILE.name}' found.")

    if not check_edl_device():
        sys.exit(1)

    patched_devinfo = OUTPUT_DP_DIR / "devinfo.img"
    patched_persist = OUTPUT_DP_DIR / "persist.img"

    if not patched_devinfo.exists() and not patched_persist.exists():
         print(f"[!] Error: Neither 'devinfo.img' nor 'persist.img' found inside '{OUTPUT_DP_DIR.name}'.", file=sys.stderr)
         sys.exit(1)

    edl_ng_exe = TOOLS_DIR / "edl-ng.exe"
    if not edl_ng_exe.exists():
        print(f"[!] 'edl-ng.exe' not found. Please run 'read_edl.bat' first to download it.", file=sys.stderr)
        sys.exit(1)

    commands_executed = False
    
    try:
        if patched_devinfo.exists():
            print(f"\n[*] Attempting to write 'devinfo' partition with '{patched_devinfo.name}'...")
            run_command([
                str(edl_ng_exe),
                "--loader", str(EDL_LOADER_FILE),
                "write-part", "devinfo", str(patched_devinfo)
            ])
            print("[+] Successfully wrote 'devinfo'.")
            commands_executed = True
        else:
            print(f"\n[*] 'devinfo.img' not found in '{OUTPUT_DP_DIR.name}'. Skipping write.")

        if patched_persist.exists():
            print(f"\n[*] Attempting to write 'persist' partition with '{patched_persist.name}'...")
            run_command([
                str(edl_ng_exe),
                "--loader", str(EDL_LOADER_FILE),
                "write-part", "persist", str(patched_persist)
            ])
            print("[+] Successfully wrote 'persist'.")
            commands_executed = True
        else:
            print(f"\n[*] 'persist.img' not found in '{OUTPUT_DP_DIR.name}'. Skipping write.")

        if commands_executed:
            print("\n[*] Operations complete. Resetting device...")
            run_command([
                str(edl_ng_exe),
                "--loader", str(EDL_LOADER_FILE),
                "reset"
            ])
            print("[+] Device reset command sent.")
        else:
            print("\n[!] No partitions were written. Skipping reset.")

    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[!] An error occurred during the EDL write/reset operation: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n" + "="*61)
    print("  FRIENDLY REMINDER:")
    print("  Please ensure you have a safe backup of your original")
    print("  'devinfo.img' and 'persist.img' files before proceeding")
    print("  with any manual flashing operations.")
    print("="*61)

    print("\n--- EDL Write Process Finished ---")


def show_image_info(files):
    """Displays information about image files, searching directories for .img files."""
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
        info_header = f"Processing file: {file_path.name}\n---------------------------------"
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
        except subprocess.CalledProcessError as e:
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

def patch_chained_image_rollback(image_name, current_rb_index, new_image_path, patched_image_path):
    """
    Helper function to patch the rollback index of a chained partition image 
    (like boot.img) using add_hash_footer.
    This bypasses the device's anti-rollback protection.
    """
    key_map = {
        "2597c218aae470a130f61162feaae70afd97f011": AVB_DIR / "testkey_rsa4096.pem",
        "cdbb77177f731920bbe0a0f94f84d9038ae0617d": AVB_DIR / "testkey_rsa2048.pem"
    }

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
        
        key_file = key_map.get(info['pubkey_sha1'])
        if not key_file:
            raise KeyError(f"Unknown public key SHA1 {info['pubkey_sha1']} in {new_image_path.name}")

        shutil.copy(new_image_path, patched_image_path)
        
        add_footer_cmd = [
            str(PYTHON_EXE), str(AVBTOOL_PY), "add_hash_footer",
            "--image", str(patched_image_path), 
            "--key", str(key_file),
            "--algorithm", info['algorithm'], 
            "--partition_size", info['partition_size'],
            "--partition_name", info['name'], 
            "--salt", info['salt'],
            "--rollback_index", str(current_rb_index),
            *info.get('props_args', [])
        ]
        
        if 'flags' in info:
            add_footer_cmd.extend(["--flags", info.get('flags', '0')])

        run_command(add_footer_cmd)
        print(f"[+] Successfully patched {image_name}.")

    except (KeyError, subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[!] Error processing {image_name}: {e}", file=sys.stderr)
        raise

def patch_vbmeta_image_rollback(image_name, current_rb_index, new_image_path, patched_image_path):
    """
    Helper function to patch the rollback index of a main vbmeta image 
    (like vbmeta_system.img) using make_vbmeta_image.
    This bypasses the device's anti-rollback protection.
    """
    key_map = {
        "2597c218aae470a130f61162feaae70afd97f011": AVB_DIR / "testkey_rsa4096.pem",
        "cdbb77177f731920bbe0a0f94f84d9038ae0617d": AVB_DIR / "testkey_rsa2048.pem"
    }

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
        
        key_file = key_map.get(info['pubkey_sha1'])
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

def anti_rollback():
    """Bypasses anti-rollback protection by patching downgrade firmware images."""
    print("--- Anti-Anti-Rollback Patcher ---")
    print("This tool patches new firmware images (for downgrading)")
    print("to match your currently installed firmware's rollback index.")
    print("-" * 50)
    check_dependencies()
    
    if OUTPUT_ANTI_ROLLBACK_DIR.exists():
        shutil.rmtree(OUTPUT_ANTI_ROLLBACK_DIR)
    OUTPUT_ANTI_ROLLBACK_DIR.mkdir(exist_ok=True)

    current_files = ["boot.img", "vbmeta_system.img"]
    current_prompt = (
        "[STEP 1] Place the firmware files from your CURRENTLY INSTALLED OS version\n"
        "         (e.g., from your device or a backup) into the folder below."
    )
    wait_for_files(INPUT_CURRENT_DIR, current_files, current_prompt)
    
    print("\n[*] Extracting current firmware rollback indices...")
    try:
        current_boot_info = extract_image_avb_info(INPUT_CURRENT_DIR / "boot.img")
        current_boot_rb = int(current_boot_info.get('rollback', '0'))
        
        current_vbmeta_info = extract_image_avb_info(INPUT_CURRENT_DIR / "vbmeta_system.img")
        current_vbmeta_rb = int(current_vbmeta_info.get('rollback', '0'))
    except Exception as e:
        print(f"[!] Error reading current image info: {e}. Please check files.", file=sys.stderr)
        return

    print(f"  > Current Boot Index: {current_boot_rb}")
    print(f"  > Current VBMeta System Index: {current_vbmeta_rb}")

    new_files = ["boot.img", "vbmeta_system.img"]
    new_prompt = (
        "[STEP 2] Place the NEW firmware files you want to FLASH\n"
        "         (e.g., the downgrade firmware) into the folder below."
    )
    wait_for_files(INPUT_NEW_DIR, new_files, new_prompt)
    
    print("\n[*] Extracting new firmware rollback indices...")
    try:
        new_boot_info = extract_image_avb_info(INPUT_NEW_DIR / "boot.img")
        new_boot_rb = int(new_boot_info.get('rollback', '0'))
        
        new_vbmeta_info = extract_image_avb_info(INPUT_NEW_DIR / "vbmeta_system.img")
        new_vbmeta_rb = int(new_vbmeta_info.get('rollback', '0'))
    except Exception as e:
        print(f"[!] Error reading new image info: {e}. Please check files.", file=sys.stderr)
        return

    print(f"  > New Boot Index: {new_boot_rb}")
    print(f"  > New VBMeta System Index: {new_vbmeta_rb}")

    if new_boot_rb >= current_boot_rb and new_vbmeta_rb >= current_vbmeta_rb:
        print("\n[+] New firmware indices are the same or higher.")
        print("This is not a downgrade. No patching is necessary.")
        print("Press Enter to exit.")
        try:
            input()
        except EOFError:
            pass
        return

    print("\n[!] Downgrade detected! Bypassing anti-rollback...")
    
    try:
        patch_chained_image_rollback(
            image_name="boot.img",
            current_rb_index=current_boot_rb,
            new_image_path=(INPUT_NEW_DIR / "boot.img"),
            patched_image_path=(OUTPUT_ANTI_ROLLBACK_DIR / "boot.img")
        )
        
        print("-" * 20)

        patch_vbmeta_image_rollback(
            image_name="vbmeta_system.img",
            current_rb_index=current_vbmeta_rb,
            new_image_path=(INPUT_NEW_DIR / "vbmeta_system.img"),
            patched_image_path=(OUTPUT_ANTI_ROLLBACK_DIR / "vbmeta_system.img")
        )

        print("\n" + "=" * 61)
        print("  SUCCESS!")
        print(f"  Anti-rollback patched images are in '{OUTPUT_ANTI_ROLLBACK_DIR.name}'.")
        print(f"  You can now flash these images to downgrade.")
        print("=" * 61)

    except Exception as e:
        print(f"\n[!] An error occurred during patching: {e}", file=sys.stderr)
        shutil.rmtree(OUTPUT_ANTI_ROLLBACK_DIR) # Clean up partial output

def main():
    """Main function to parse arguments and call appropriate functions."""
    parser = argparse.ArgumentParser(description="Android Image Patcher and AVB Tool.")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")

    subparsers.add_parser("convert", help="Convert vendor_boot region and remake vbmeta.")
    subparsers.add_parser("root", help="Patch boot.img with KernelSU.")
    subparsers.add_parser("edit_dp", help="Edit devinfo and persist images.")
    subparsers.add_parser("read_edl", help="Read devinfo and persist images via EDL.")
    subparsers.add_parser("write_edl", help="Write patched devinfo and persist images via EDL.")
    subparsers.add_parser("anti_rollback", help="Bypass anti-rollback (downgrade) protection by patching firmware indices.")
    parser_info = subparsers.add_parser("info", help="Display AVB info for image files or directories.")
    parser_info.add_argument("files", nargs='+', help="Image file(s) or folder(s) to inspect.")

    args = parser.parse_args()

    try:
        if args.command == "convert":
            convert_images()
        elif args.command == "root":
            root_boot_only()
        elif args.command == "edit_dp":
            edit_devinfo_persist()
        elif args.command == "read_edl":
            read_edl()
        elif args.command == "write_edl":
            write_edl()
        elif args.command == "anti_rollback":
            anti_rollback()
        elif args.command == "info":
            show_image_info(args.files)
    except (subprocess.CalledProcessError, FileNotFoundError, RuntimeError, SystemExit) as e:
        if not isinstance(e, SystemExit):
            print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
    except KeyError as e:
        print(f"\nAn error occurred while processing image info: {e}", file=sys.stderr)
        print("Please check if the image is valid and contains the necessary AVB metadata.", file=sys.stderr)

    finally:
        print()
        if platform.system() == "Windows":
            os.system("pause")

if __name__ == "__main__":
    main()