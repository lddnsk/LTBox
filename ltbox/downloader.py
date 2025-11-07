import platform
import shutil
import subprocess
import sys
import zipfile

from ltbox.constants import *
from ltbox import utils

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
            utils.run_command(fetch_command, capture=True)

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
    utils.run_command(fetch_command)

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
        print("[+] KernelSU Next Manager APK already exists. Skipping download.")
    else:
        ksu_apk_command = [
            str(fetch_exe), "--repo", f"https://github.com/{KSU_APK_REPO}", "--tag", KSU_APK_TAG,
            "--release-asset", ".*\\.apk", str(target_dir)
        ]
        utils.run_command(ksu_apk_command)
        print("[+] KernelSU Next Manager APKs downloaded to the main directory (if found).")