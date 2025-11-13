import shutil
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from ..constants import *
from .. import utils, imgpatch

def read_anti_rollback(dumped_boot_path: Path, dumped_vbmeta_path: Path, lang: Optional[Dict[str, str]] = None) -> Tuple[str, int, int]:
    lang = lang or {}
    print(lang.get("act_start_arb", "--- Anti-Rollback Status Check ---"))
    utils.check_dependencies(lang=lang)
    
    current_boot_rb = 0
    current_vbmeta_rb = 0
    
    print(lang.get("act_arb_step1", "\n--- [STEP 1] Parsing Rollback Indices from DUMPED IMAGES ---"))
    try:
        if not dumped_boot_path.exists() or not dumped_vbmeta_path.exists():
            raise FileNotFoundError(lang.get("act_err_dumped_missing", "Dumped boot/vbmeta images not found."))
        
        print(lang.get("act_read_dumped_boot", "[*] Reading from: {name}").format(name=dumped_boot_path.name))
        boot_info = imgpatch.extract_image_avb_info(dumped_boot_path, lang=lang)
        current_boot_rb = int(boot_info.get('rollback', '0'))
        
        print(lang.get("act_read_dumped_vbmeta", "[*] Reading from: {name}").format(name=dumped_vbmeta_path.name))
        vbmeta_info = imgpatch.extract_image_avb_info(dumped_vbmeta_path, lang=lang)
        current_vbmeta_rb = int(vbmeta_info.get('rollback', '0'))
        
    except Exception as e:
        print(lang.get("act_err_avb_info", "[!] Error extracting AVB info from dumps: {e}").format(e=e), file=sys.stderr)
        print(lang.get("act_arb_error", "\n--- Status Check Complete: ERROR ---"))
        return 'ERROR', 0, 0

    print(lang.get("act_curr_boot_idx", "  > Current Device Boot Index: {idx}").format(idx=current_boot_rb))
    print(lang.get("act_curr_vbmeta_idx", "  > Current Device VBMeta System Index: {idx}").format(idx=current_vbmeta_rb))

    print(lang.get("act_arb_step2", "\n--- [STEP 2] Comparing New ROM Indices ---"))
    print(lang.get("act_extract_new_indices", "\n[*] Extracting new ROM's rollback indices (from 'image' folder)..."))
    new_boot_img = IMAGE_DIR / "boot.img"
    new_vbmeta_img = IMAGE_DIR / "vbmeta_system.img"

    if not new_boot_img.exists() or not new_vbmeta_img.exists():
        print(lang.get("act_err_new_rom_missing", "[!] Error: 'boot.img' or 'vbmeta_system.img' not found in '{dir}' folder.").format(dir=IMAGE_DIR.name))
        print(lang.get("act_arb_missing_new", "\n--- Status Check Complete: MISSING_NEW ---"))
        return 'MISSING_NEW', 0, 0
        
    new_boot_rb = 0
    new_vbmeta_rb = 0
    try:
        new_boot_info = imgpatch.extract_image_avb_info(new_boot_img, lang=lang)
        new_boot_rb = int(new_boot_info.get('rollback', '0'))
        
        new_vbmeta_info = imgpatch.extract_image_avb_info(new_vbmeta_img, lang=lang)
        new_vbmeta_rb = int(new_vbmeta_info.get('rollback', '0'))
    except Exception as e:
        print(lang.get("act_err_read_new_info", "[!] Error reading new image info: {e}. Please check files.").format(e=e), file=sys.stderr)
        print(lang.get("act_arb_error", "\n--- Status Check Complete: ERROR ---"))
        return 'ERROR', 0, 0

    print(lang.get("act_new_boot_idx", "  > New ROM's Boot Index: {idx}").format(idx=new_boot_rb))
    print(lang.get("act_new_vbmeta_idx", "  > New ROM's VBMeta System Index: {idx}").format(idx=new_vbmeta_rb))

    if new_boot_rb == current_boot_rb and new_vbmeta_rb == current_vbmeta_rb:
        print(lang.get("act_arb_match", "\n[+] Indices are identical. No Anti-Rollback patch needed."))
        status = 'MATCH'
    else:
        print(lang.get("act_arb_patch_req", "\n[*] Indices are different (higher or lower). Patching is REQUIRED."))
        status = 'NEEDS_PATCH'
    
    print(lang.get("act_arb_complete", "\n--- Status Check Complete: {status} ---").format(status=status))
    return status, current_boot_rb, current_vbmeta_rb

def patch_anti_rollback(comparison_result: Tuple[str, int, int], lang: Optional[Dict[str, str]] = None) -> None:
    lang = lang or {}
    print(lang.get("act_start_arb_patch", "--- Anti-Rollback Patcher ---"))
    utils.check_dependencies(lang=lang)

    if OUTPUT_ANTI_ROLLBACK_DIR.exists():
        shutil.rmtree(OUTPUT_ANTI_ROLLBACK_DIR)
    OUTPUT_ANTI_ROLLBACK_DIR.mkdir(exist_ok=True)
    
    try:
        if comparison_result:
            print(lang.get("act_use_pre_arb", "[*] Using pre-computed Anti-Rollback status..."))
            status, current_boot_rb, current_vbmeta_rb = comparison_result
        else:
            print(lang.get("act_err_no_cmp", "[!] No comparison result provided. Aborting."))
            return

        if status != 'NEEDS_PATCH':
            print(lang.get("act_arb_no_patch", "\n[!] No patching is required or files are missing. Aborting patch."))
            return

        print(lang.get("act_arb_step3", "\n--- [STEP 3] Patching New ROM ---"))
        
        imgpatch.patch_chained_image_rollback(
            image_name="boot.img",
            current_rb_index=current_boot_rb,
            new_image_path=(IMAGE_DIR / "boot.img"),
            patched_image_path=(OUTPUT_ANTI_ROLLBACK_DIR / "boot.img"),
            lang=lang
        )
        
        print("-" * 20)
        
        imgpatch.patch_vbmeta_image_rollback(
            image_name="vbmeta_system.img",
            current_rb_index=current_vbmeta_rb,
            new_image_path=(IMAGE_DIR / "vbmeta_system.img"),
            patched_image_path=(OUTPUT_ANTI_ROLLBACK_DIR / "vbmeta_system.img"),
            lang=lang
        )

        print("\n" + "=" * 61)
        print(lang.get("act_success", "  SUCCESS!"))
        print(lang.get("act_arb_patched_ready", "  Anti-rollback patched images are in '{dir}'.").format(dir=OUTPUT_ANTI_ROLLBACK_DIR.name))
        print(lang.get("act_arb_next_step", "  You can now run 'Write Anti-Rollback' (Menu 8)."))
        print("=" * 61)

    except Exception as e:
        print(lang.get("act_err_arb_patch", "\n[!] An error occurred during patching: {e}").format(e=e), file=sys.stderr)
        shutil.rmtree(OUTPUT_ANTI_ROLLBACK_DIR)