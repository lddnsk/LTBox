# Android BOOT & VBMETA Patcher

## ⚠️ Disclaimer

**This project is for educational purposes ONLY.**

Modifying your device's boot images carries significant risks, including but not limited to, bricking your device, data loss, or voiding your warranty. The author **assumes no liability** and is not responsible for any **damage or consequence** that may occur to **your device or anyone else's device** from using these scripts.

**You are solely responsible for any consequences. Use at your own absolute risk.**

This set of scripts automates two main tasks:
1.  Converting the region code for `vendor_boot.img` and remaking the corresponding `vbmeta.img`.
2.  Enabling root by replacing the kernel in `boot.img` with [patched one](https://github.com/WildKernels/GKI_KernelSU_SUSFS).

## Prerequisites

Before you begin, place the required files from your device's stock firmware into the main directory:

* For `vendor_boot`/`vbmeta` conversion: `vendor_boot.img` and `vbmeta.img`.
* For rooting: `boot.img`.

## How to Use

1.  **Place Images:** Put the necessary `.img` files into the root folder.
2.  **Install Dependencies:** Run `install.bat` once to download and set up all required tools.
3.  **Run the Script:**
    * To convert `vendor_boot` and remake `vbmeta`, run **`convert.bat`**. The results will be in the `output` folder.
    * To enable root, run **`only_root.bat`**. The result will be in the `output_root` folder.
4.  **Flash the Images:** After a script finishes, flash the new `.img` file(s) from the appropriate output folder to your device using `fastboot`.

## Script Descriptions

* **`install.bat`**: Downloads and sets up all necessary tools (Python, avbtool, etc.).
* **`convert.bat`**: Handles the `vendor_boot` region code conversion and remakes `vbmeta.img`.
* **`only_root.bat`**: Enables root by replacing the kernel in `boot.img` with a WKSU & SUSFS patched version.
* **`info.bat`**: Drag & drop `.img` file(s) or folder(s) onto this script to see AVB information.