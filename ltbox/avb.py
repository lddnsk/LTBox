import re
import shutil
import subprocess
from pathlib import Path

from ltbox.constants import *
from ltbox import utils

# --- AVB (Android Verified Boot) Helpers ---
def extract_image_avb_info(image_path):
    info_proc = utils.run_command(
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

    utils.run_command(add_footer_cmd)
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
        
        utils.run_command(remake_cmd)
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