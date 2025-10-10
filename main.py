import os
import sys
import shutil
import subprocess
import argparse
import requests
import zipfile
import platform
import re
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.resolve()
TOOLS_DIR = BASE_DIR / "tools"
PYTHON_EXE = BASE_DIR / "python3" / "python.exe"
KEY_DIR = BASE_DIR / "key"
AVBTOOL_PY = TOOLS_DIR / "avbtool.py"
EDIT_VNDRBOOT_PY = TOOLS_DIR / "edit_vndrboot.py"
PARSE_INFO_PY = TOOLS_DIR / "parse_info.py"
GET_KERNEL_VER_PY = TOOLS_DIR / "get_kernel_ver.py"

KSU_APK_REPO = "https://github.com/KernelSU-Next/KernelSU-Next"
KSU_APK_TAG = "v1.1.1"

RELEASE_OWNER = "WildKernels"
RELEASE_REPO = "GKI_KernelSU_SUSFS"
RELEASE_TAG = "v1.5.9-r36"
REPO_URL = f"https://github.com/{RELEASE_OWNER}/{RELEASE_REPO}"

ANYKERNEL_ZIP_FILENAME = "AnyKernel3.zip"

def run_command(command, shell=False, check=True):
    try:
        env = os.environ.copy()
        env['PATH'] = str(TOOLS_DIR) + os.pathsep + env['PATH']

        process = subprocess.run(
            command, shell=shell, check=check, capture_output=True, text=True, encoding='utf-8', errors='ignore', env=env
        )
        if process.stdout:
            print(process.stdout.strip())
        if process.stderr:
            print(process.stderr.strip(), file=sys.stderr)
        return process
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {' '.join(map(str, command))}", file=sys.stderr)
        print(f"Return code: {e.returncode}", file=sys.stderr)
        if e.stdout:
            print(f"Stdout:\n{e.stdout.strip()}", file=sys.stderr)
        if e.stderr:
            print(f"Stderr:\n{e.stderr.strip()}", file=sys.stderr)
        raise
    except FileNotFoundError:
        print(f"Error: Command not found - {command[0]}", file=sys.stderr)
        raise

def get_platform_executable(name):
    system = platform.system()
    if system == "Windows":
        return TOOLS_DIR / f"{name}.exe"
    elif system == "Linux":
        return TOOLS_DIR / f"{name}-linux"
    elif system == "Darwin":
        return TOOLS_DIR / f"{name}-macos"
    else:
        raise RuntimeError(f"Unsupported operating system: {system}")

def check_dependencies():
    print("--- Checking for required files ---")
    dependencies = {
        "Python Environment": PYTHON_EXE,
        "RSA4096 Key": KEY_DIR / "testkey_rsa4096.pem",
        "RSA2048 Key": KEY_DIR / "testkey_rsa2048.pem",
        "avbtool": AVBTOOL_PY,
        "fetch tool": get_platform_executable("fetch")
    }
    for name, path in dependencies.items():
        if not path.exists():
            print(f"[!] Error: Dependency '{name}' is missing.")
            print("Please run 'install.bat' first to download all required files.")
            sys.exit(1)
    print("[+] All dependencies are present.")
    print()

def patch_boot_with_root():
    print("--- Starting boot.img patching process ---")
    try:
        magiskboot_exe = get_platform_executable("magiskboot")
        fetch_exe = get_platform_executable("fetch")

        if not magiskboot_exe.exists():
            print(f"[!] '{magiskboot_exe.name}' not found. Attempting to download...")
            if platform.system() == "Windows":
                url = 'https://github.com/CYRUS-STUDIO/MagiskBootWindows/raw/refs/heads/main/magiskboot.exe'
                response = requests.get(url, stream=True)
                response.raise_for_status()
                with open(magiskboot_exe, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                print("[+] Download successful.")
            else:
                print(f"[!] Auto-download for {platform.system()} is not supported. Please add it to the 'tools' folder manually.")
                sys.exit(1)

        if not fetch_exe.exists():
             print(f"[!] '{fetch_exe.name}' not found. Please run install.bat")
             sys.exit(1)


    except (RuntimeError, requests.RequestException) as e:
        print(e, file=sys.stderr)
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

    work_dir = BASE_DIR / "patch_work"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir()

    original_cwd = os.getcwd()
    os.chdir(work_dir)

    try:
        shutil.copy(boot_img, work_dir)

        print("\n[1/8] Unpacking boot image...")
        run_command([str(magiskboot_exe), "unpack", "boot.img"])
        if not (work_dir / "kernel").exists():
            print("[!] Failed to unpack boot.img. The image might be invalid.")
            sys.exit(1)
        print("[+] Unpack successful.")

        print("\n[2/8] Verifying kernel version...")
        result = run_command([str(PYTHON_EXE), str(GET_KERNEL_VER_PY), "kernel"])
        full_kernel_string = result.stdout.strip()
        print(f"[+] Found version string: {full_kernel_string}")

        kernel_version_match = re.match(r"(\d+\.\d+\.\d+)", full_kernel_string)
        if not kernel_version_match:
            print("[!] Could not extract a valid kernel version (e.g., x.y.z) from string.")
            sys.exit(1)
        target_kernel_version = kernel_version_match.group(1)
        print(f"[+] Target kernel version for download: {target_kernel_version}")

        print("\n[3/8] Downloading GKI Kernel with fetch...")

        asset_pattern = f".*{target_kernel_version}.*AnyKernel3.zip"

        fetch_command = [
            str(fetch_exe),
            "--repo", REPO_URL,
            "--tag", RELEASE_TAG,
            "--release-asset", asset_pattern,
            "."
        ]

        run_command(fetch_command)

        downloaded_files = list(Path(".").glob(f"*{target_kernel_version}*AnyKernel3.zip"))
        if not downloaded_files:
            print(f"[!] Failed to download AnyKernel3.zip for kernel {target_kernel_version}.")
            sys.exit(1)

        downloaded_zip = downloaded_files[0]
        shutil.move(downloaded_zip, ANYKERNEL_ZIP_FILENAME)
        print("[+] Download complete.")


        print("\n[4/8] Extracting new kernel image...")
        extracted_kernel_dir = work_dir / "extracted_kernel"
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
        if not (work_dir / "new-boot.img").exists():
            print("[!] Failed to repack the boot image.")
            sys.exit(1)
        shutil.move("new-boot.img", BASE_DIR / "boot.root.img")
        print("[+] Repack successful.")

        print("\n[7/8] Downloading KernelSU Manager APKs...")
        ksu_apk_command = [
            str(fetch_exe),
            "--repo", KSU_APK_REPO,
            "--tag", KSU_APK_TAG,
            "--release-asset", ".*\\.apk",
            str(BASE_DIR)
        ]
        run_command(ksu_apk_command)
        print(f"[+] KernelSU Manager APKs downloaded to the main directory (if any were found).")


    finally:
        os.chdir(original_cwd)
        if work_dir.exists():
            shutil.rmtree(work_dir)
        if boot_img.exists():
            boot_img.unlink()
        print("\n--- Cleaning up ---")

    print("\n" + "=" * 61)
    print("  SUCCESS!")
    print(f"  Patched image has been saved as: {BASE_DIR / 'boot.root.img'}")
    print("=" * 61)
    print("\n--- Handing over to convert process ---\n")


def convert_images(with_root=False):
    if with_root:
        patch_boot_with_root()

    check_dependencies()

    print("[*] Cleaning up old folders...")
    if (BASE_DIR / "output").exists():
        shutil.rmtree(BASE_DIR / "output")
    print()

    print("--- Backing up original images ---")
    vendor_boot_img = BASE_DIR / "vendor_boot.img"
    vbmeta_img = BASE_DIR / "vbmeta.img"

    if not vendor_boot_img.exists():
        print("[!] 'vendor_boot.img' not found! Aborting.")
        sys.exit(1)
    if not vbmeta_img.exists():
        print("[!] 'vbmeta.img' not found! Aborting.")
        sys.exit(1)

    vendor_boot_bak = BASE_DIR / "vendor_boot.bak.img"
    vbmeta_bak = BASE_DIR / "vbmeta.bak.img"
    shutil.move(vendor_boot_img, vendor_boot_bak)
    shutil.copy(vbmeta_img, vbmeta_bak)
    print("[+] Backup complete.\n")

    print("--- Starting PRC/ROW Conversion ---")
    run_command([str(PYTHON_EXE), str(EDIT_VNDRBOOT_PY), str(vendor_boot_bak)])

    vendor_boot_prc = BASE_DIR / "vendor_boot_prc.img"
    print("\n[*] Verifying conversion result...")
    if not vendor_boot_prc.exists():
        print("[!] 'vendor_boot_prc.img' was not created. No changes made.")
        sys.exit(1)
    print("[+] Conversion to PRC successful.\n")

    print("--- Extracting Image Information ---")
    info_proc = run_command([
        str(PYTHON_EXE), str(PARSE_INFO_PY), str(vendor_boot_bak), str(AVBTOOL_PY), str(vbmeta_bak)
    ])

    img_info = dict(line.split('=', 1) for line in info_proc.stdout.strip().split('\n') if '=' in line)

    prop_val_clean = img_info['PROP_VAL'][1:-1]

    print("\n--- Adding Hash Footer to vendor_boot ---")
    prop_val_file = BASE_DIR / "prop_val.tmp"
    with open(prop_val_file, "w", encoding='utf-8') as f:
        f.write(prop_val_clean)

    add_hash_footer_cmd = [
        str(PYTHON_EXE), str(AVBTOOL_PY), "add_hash_footer",
        "--image", str(vendor_boot_prc),
        "--partition_size", img_info['IMG_SIZE'],
        "--partition_name", "vendor_boot",
        "--rollback_index", "0",
        "--salt", img_info['SALT'],
        "--prop_from_file", f"{img_info['PROP_KEY']}:{prop_val_file}"
    ]
    run_command(add_hash_footer_cmd)

    if prop_val_file.exists():
        prop_val_file.unlink()
    print()

    key_file = ""
    public_key = img_info.get('PUBLIC_KEY')
    if public_key == "2597c218aae470a130f61162feaae70afd97f011":
        key_file = KEY_DIR / "testkey_rsa4096.pem"
    elif public_key == "cdbb77177f731920bbe0a0f94f84d9038ae0617d":
        key_file = KEY_DIR / "testkey_rsa2048.pem"

    if with_root:
        print("--- Processing boot image ---")
        boot_bak_img = BASE_DIR / "boot.bak.img"
        boot_info_proc = run_command([str(PYTHON_EXE), str(AVBTOOL_PY), "info_image", "--image", str(boot_bak_img)])

        boot_info = {}
        boot_props_args = []
        for line in boot_info_proc.stdout.strip().split('\n'):
            line = line.strip()
            if line.startswith("Image size:"):
                boot_info['size'] = line.split()[-2]
            elif line.startswith("Partition Name:"):
                boot_info['name'] = line.split()[-1]
            elif line.startswith("Salt:"):
                boot_info['salt'] = line.split()[-1]
            elif line.startswith("Rollback Index:"):
                boot_info['rollback'] = line.split()[-1]
            elif line.startswith("Prop:"):
                parts = line.split('->')
                key = parts[0].split(':')[-1].strip()
                val = parts[1].strip()[1:-1]
                boot_props_args.extend(["--prop", f"{key}:{val}"])

        print("\n[*] Adding new hash footer to 'boot.root.img'...")
        boot_root_img = BASE_DIR / "boot.root.img"
        add_footer_cmd = [
            str(PYTHON_EXE), str(AVBTOOL_PY), "add_hash_footer",
            "--image", str(boot_root_img),
            "--key", str(key_file),
            "--algorithm", img_info['ALGORITHM'],
            "--partition_size", boot_info['size'],
            "--partition_name", boot_info['name'],
            "--rollback_index", boot_info['rollback'],
            "--salt", boot_info['salt']
        ] + boot_props_args
        run_command(add_footer_cmd)
        print()

    print("--- Re-signing vbmeta.img ---")
    print("[*] Verifying vbmeta key...")
    if not key_file:
        print(f"[!] Public key '{public_key}' did not match known keys. Aborting.")
        sys.exit(1)
    print(f"[+] Matched {key_file.name}.")

    print("\n[*] Re-signing 'vbmeta.img' using backup descriptors...")
    resign_cmd = [
        str(PYTHON_EXE), str(AVBTOOL_PY), "make_vbmeta_image",
        "--output", str(vbmeta_img),
        "--key", str(key_file),
        "--algorithm", img_info['ALGORITHM'],
        "--padding_size", "8192",
        "--include_descriptors_from_image", str(vbmeta_bak),
        "--include_descriptors_from_image", str(vendor_boot_prc)
    ]
    run_command(resign_cmd)
    print()

    print("--- Finalizing ---")
    print("[*] Renaming final images...")
    final_vendor_boot = BASE_DIR / "vendor_boot.img"
    shutil.move(vendor_boot_prc, final_vendor_boot)

    final_images = [final_vendor_boot, vbmeta_img]
    if with_root:
        final_boot = BASE_DIR / "boot.img"
        shutil.move(BASE_DIR / "boot.root.img", final_boot)
        final_images.append(final_boot)

    print("\n[*] Moving final images to 'output' folder...")
    output_dir = BASE_DIR / "output"
    output_dir.mkdir(exist_ok=True)
    for img in final_images:
        shutil.move(img, output_dir / img.name)

    print("\n[*] Moving backup files to 'backup' folder...")
    backup_dir = BASE_DIR / "backup"
    backup_dir.mkdir(exist_ok=True)
    for bak_file in BASE_DIR.glob("*.bak.img"):
        shutil.move(bak_file, backup_dir / bak_file.name)
    print()

    print("=" * 61)
    print("  SUCCESS!")
    print("  Final images have been saved to the 'output' folder.")
    print("=" * 61)

def show_image_info(files):
    output_lines = []

    def add_to_output(text):
        print(text)
        output_lines.append(text)

    add_to_output("\n" + "=" * 42)
    add_to_output("  Sorted and Processing Images...")
    add_to_output("=" * 42 + "\n")

    sorted_files = sorted(files)

    for f in sorted_files:
        file_path = Path(f).resolve()
        
        add_to_output(f"Processing file: {file_path.name}")
        add_to_output("---------------------------------")

        if not file_path.exists():
            add_to_output(f"File not found: {file_path}")
            add_to_output("---------------------------------\n")
            continue

        try:
            env = os.environ.copy()
            env['PATH'] = str(TOOLS_DIR) + os.pathsep + env['PATH']
            process = subprocess.run(
                [str(PYTHON_EXE), str(AVBTOOL_PY), "info_image", "--image", str(file_path)],
                capture_output=True, text=True, encoding='utf-8', errors='ignore', env=env, check=True
            )
            
            if process.stdout:
                add_to_output(process.stdout.strip())
            if process.stderr:
                print(process.stderr.strip(), file=sys.stderr)

        except subprocess.CalledProcessError as e:
            error_message = f"Failed to get info from {file_path.name}"
            add_to_output(error_message)
            if e.stderr:
                print(e.stderr.strip(), file=sys.stderr)
        
        add_to_output("---------------------------------\n")
    
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        output_filename = BASE_DIR / f"{timestamp}.txt"
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(output_lines))
        print(f"[*] Image info saved to: {output_filename}")
    except IOError as e:
        print(f"[!] Error saving info to file: {e}", file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(description="Android vendor_boot Patcher and vbmeta Resigner.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parser_convert = subparsers.add_parser("convert", help="Convert vendor_boot and re-sign vbmeta.")
    parser_convert.add_argument("--with-root", action="store_true", help="Patch boot.img with KernelSU before converting.")

    parser_info = subparsers.add_parser("info", help="Display information about image files.")
    parser_info.add_argument("files", nargs='+', help="Image file(s) to inspect.")

    args = parser.parse_args()

    try:
        if args.command == "convert":
            convert_images(args.with_root)
        elif args.command == "info":
            show_image_info(args.files)
    except (subprocess.CalledProcessError, FileNotFoundError, SystemExit) as e:
        if isinstance(e, SystemExit):
            pass
        else:
            print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
    finally:
        print()
        os.system("pause")


if __name__ == "__main__":
    main()