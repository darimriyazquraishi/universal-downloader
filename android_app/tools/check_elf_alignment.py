#!/usr/bin/env python3
"""Strictly validate native shared-library ELF alignment inside an Android APK.

This project currently builds arm64-v8a only. The validator intentionally fails
closed: missing .so files, malformed ELF files, unexpected architectures, and
uninspectable program headers all fail validation instead of being skipped.
"""

from __future__ import annotations

import argparse
import struct
import sys
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple, Union

PAGE_SIZE = 16 * 1024
PT_LOAD = 1
ABI_TO_MACHINE = {
    "armeabi-v7a": 40,  # EM_ARM
    "arm64-v8a": 183,   # EM_AARCH64
    "x86": 3,           # EM_386
    "x86_64": 62,       # EM_X86_64
}


def inspect_elf(data: bytes, name: str = "<memory>", expected_abi: str = "arm64-v8a") -> List[str]:
    """Return validation errors for an ELF shared library; an empty list means valid."""
    errors: List[str] = []
    expected_machine = ABI_TO_MACHINE.get(expected_abi)
    if expected_machine is None:
        return [f"Unsupported target ABI {expected_abi!r}"]

    if len(data) < 64:
        return [f"{name}: ELF file is shorter than the 64-byte ELF64 header"]
    if data[:4] != b"\x7fELF":
        return [f"{name}: .so entry is not an ELF file"]
    if data[4] != 2:
        return [f"{name}: expected ELFCLASS64 (64-bit), got class byte {data[4]}"]
    if data[5] != 1:
        return [f"{name}: expected little-endian ELF data, got data byte {data[5]}"]
    if data[6] != 1:
        return [f"{name}: invalid or unsupported ELF identification version {data[6]}"]

    try:
        e_type = struct.unpack_from("<H", data, 16)[0]
        e_machine = struct.unpack_from("<H", data, 18)[0]
        e_version = struct.unpack_from("<I", data, 20)[0]
        e_phoff = struct.unpack_from("<Q", data, 32)[0]
        e_ehsize = struct.unpack_from("<H", data, 52)[0]
        e_phentsize = struct.unpack_from("<H", data, 54)[0]
        e_phnum = struct.unpack_from("<H", data, 56)[0]
    except struct.error as exc:
        return [f"{name}: malformed ELF header: {exc}"]

    if e_type != 3:  # ET_DYN, expected for shared libraries
        errors.append(f"{name}: expected ET_DYN shared object (e_type=3), got {e_type}")
    if e_machine != expected_machine:
        errors.append(
            f"{name}: ELF machine {e_machine} does not match target ABI {expected_abi} "
            f"(expected e_machine={expected_machine})"
        )
    if e_version != 1:
        errors.append(f"{name}: invalid ELF header version {e_version}")
    if e_ehsize < 64:
        errors.append(f"{name}: invalid ELF64 header size {e_ehsize}")
    if e_phentsize < 56:
        errors.append(f"{name}: program-header entry size {e_phentsize} is smaller than ELF64 minimum 56")
    if e_phnum == 0:
        errors.append(f"{name}: ELF contains no program headers")
    if e_phoff > len(data) or e_phoff + e_phentsize * e_phnum > len(data):
        errors.append(f"{name}: program-header table extends beyond the file")
    if errors:
        return errors

    load_segments = 0
    for index in range(e_phnum):
        ph_offset = e_phoff + index * e_phentsize
        try:
            p_type = struct.unpack_from("<I", data, ph_offset)[0]
            if p_type != PT_LOAD:
                continue
            p_offset = struct.unpack_from("<Q", data, ph_offset + 8)[0]
            p_vaddr = struct.unpack_from("<Q", data, ph_offset + 16)[0]
            p_filesz = struct.unpack_from("<Q", data, ph_offset + 32)[0]
            p_memsz = struct.unpack_from("<Q", data, ph_offset + 40)[0]
            p_align = struct.unpack_from("<Q", data, ph_offset + 48)[0]
        except struct.error as exc:
            errors.append(f"{name}: malformed program header #{index}: {exc}")
            continue

        load_segments += 1
        if p_filesz > p_memsz:
            errors.append(f"{name}: PT_LOAD #{index} has p_filesz > p_memsz")
        if p_offset + p_filesz > len(data):
            errors.append(f"{name}: PT_LOAD #{index} file range extends beyond the ELF file")
        if p_align < PAGE_SIZE:
            errors.append(
                f"{name}: PT_LOAD #{index} p_align={p_align:#x} is smaller than 16 KB (0x4000)"
            )
            continue
        if p_align & (p_align - 1):
            errors.append(f"{name}: PT_LOAD #{index} p_align={p_align:#x} is not a power of two")
        if p_offset % p_align != p_vaddr % p_align:
            errors.append(
                f"{name}: PT_LOAD #{index} p_offset and p_vaddr are not congruent modulo p_align={p_align:#x}"
            )
        if p_offset % PAGE_SIZE != p_vaddr % PAGE_SIZE:
            errors.append(
                f"{name}: PT_LOAD #{index} is not congruent on a 16 KB boundary "
                f"(p_offset={p_offset:#x}, p_vaddr={p_vaddr:#x})"
            )

    if load_segments == 0:
        errors.append(f"{name}: ELF contains no PT_LOAD segments to validate")
    return errors


def inspect_apk(apk_path: Union[str, Path], expected_abi: str = "arm64-v8a") -> Tuple[List[Tuple[str, List[str]]], int]:
    """Validate all .so entries in an APK. Returns (per-library results, count)."""
    results: List[Tuple[str, List[str]]] = []
    apk_path = Path(apk_path)
    if expected_abi not in ABI_TO_MACHINE:
        return [(str(apk_path), [f"Unsupported target ABI {expected_abi!r}"])], 0

    try:
        with zipfile.ZipFile(apk_path) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith(".so")]
            if not names:
                return [(str(apk_path), ["APK contains no native .so libraries; refusing to pass alignment validation"])], 0

            for name in sorted(names):
                errors: List[str] = []
                parts = name.split("/")
                if len(parts) >= 3 and parts[0] == "lib":
                    found_abi = parts[1]
                    if found_abi != expected_abi:
                        errors.append(
                            f"unexpected APK ABI directory {found_abi!r}; expected {expected_abi!r}"
                        )
                try:
                    data = archive.read(name)
                except Exception as exc:  # bad CRC / unreadable compressed entry
                    results.append((name, [f"cannot read library entry: {exc}"]))
                    continue

                # python-for-android packages the Python standard library and site-packages
                # as a gzipped tarball archive named libpybundle.so in the native library
                # directory so Android extracts it during installation. It is an archive asset
                # container, not an ELF binary.
                if Path(name).name == "libpybundle.so":
                    if data[:2] == b"\x1f\x8b":
                        results.append((name, []))
                        continue
                    else:
                        errors.append(f"{name}: invalid python-for-android bundle (expected gzip archive)")
                        results.append((name, errors))
                        continue

                errors.extend(inspect_elf(data, name, expected_abi))
                results.append((name, errors))
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        return [(str(apk_path), [f"cannot inspect APK: {exc}"])], 0

    return results, len(names)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", help="Path to the APK to inspect")
    parser.add_argument("--abi", default="arm64-v8a", choices=sorted(ABI_TO_MACHINE), help="Expected native ABI")
    args = parser.parse_args(argv)

    results, count = inspect_apk(args.apk, args.abi)
    print(f"Inspecting {count} native .so file(s) in {args.apk} for 16 KB ELF alignment (ABI={args.abi})")
    failures = 0
    for name, errors in results:
        if errors:
            failures += 1
            print(f"[FAIL] {name}")
            for error in errors:
                print(f"  - {error}")
        else:
            if Path(name).name == "libpybundle.so":
                print(f"[PASS] {name}: valid python-for-android Python bundle archive (asset container)")
            else:
                print(f"[PASS] {name}: valid ELF64 {args.abi}; all PT_LOAD segments are 16 KB aligned")

    if failures or count == 0:
        print(f"ERROR: alignment validation failed ({failures} failure(s); {count} library/libraries inspected)", file=sys.stderr)
        return 1
    print(f"SUCCESS: all {count} native shared libraries passed 16 KB ELF alignment validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
