#!/usr/bin/env python3
"""Dependency-free tests for tools/check_elf_alignment.py."""
import os
import struct
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.check_elf_alignment import inspect_apk, inspect_elf


def make_elf64(p_align=16384, p_offset=0, p_vaddr=0, machine=183, elf_class=2):
    data = bytearray(120)
    data[0:4] = b"\x7fELF"
    data[4] = elf_class
    data[5] = 1  # little endian
    data[6] = 1  # current ELF identification version
    struct.pack_into("<H", data, 16, 3)  # ET_DYN shared object
    struct.pack_into("<H", data, 18, machine)
    struct.pack_into("<I", data, 20, 1)
    struct.pack_into("<Q", data, 32, 64)
    struct.pack_into("<H", data, 52, 64)
    struct.pack_into("<H", data, 54, 56)
    struct.pack_into("<H", data, 56, 1)
    # PT_LOAD, PF_R | PF_X, offset, vaddr, paddr, filesz, memsz, p_align
    struct.pack_into("<IIQQQQQQ", data, 64, 1, 5, p_offset, p_vaddr, p_vaddr, len(data), len(data), p_align)
    return bytes(data)


class TestElfAlignmentValidator(unittest.TestCase):
    def test_accepts_valid_16kb_arm64_library(self):
        self.assertEqual(inspect_elf(make_elf64(), "libvalid.so", "arm64-v8a"), [])

    def test_rejects_4kb_and_misaligned_segments(self):
        self.assertTrue(inspect_elf(make_elf64(p_align=4096), "lib4k.so", "arm64-v8a"))
        self.assertTrue(inspect_elf(make_elf64(p_vaddr=4096), "libmisaligned.so", "arm64-v8a"))

    def test_rejects_wrong_architecture_and_malformed_file(self):
        self.assertTrue(inspect_elf(make_elf64(machine=62), "libx86.so", "arm64-v8a"))
        self.assertTrue(inspect_elf(make_elf64(elf_class=1), "lib32.so", "arm64-v8a"))
        self.assertTrue(inspect_elf(b"not an ELF", "libbroken.so", "arm64-v8a"))

    def test_apk_with_no_native_libraries_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            apk = os.path.join(td, "empty.apk")
            with zipfile.ZipFile(apk, "w"):
                pass
            results, count = inspect_apk(apk, "arm64-v8a")
            self.assertEqual(count, 0)
            self.assertTrue(any(errors for _, errors in results))

    def test_apk_validates_every_library_and_fails_on_malformed_entry(self):
        with tempfile.TemporaryDirectory() as td:
            apk = os.path.join(td, "mixed.apk")
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr("lib/arm64-v8a/libvalid.so", make_elf64())
                archive.writestr("lib/arm64-v8a/libbroken.so", b"bad")
            results, count = inspect_apk(apk, "arm64-v8a")
            self.assertEqual(count, 2)
            by_name = {name: errors for name, errors in results}
            self.assertEqual(by_name["lib/arm64-v8a/libvalid.so"], [])
            self.assertTrue(by_name["lib/arm64-v8a/libbroken.so"])

    def test_unexpected_abi_directory_fails(self):
        with tempfile.TemporaryDirectory() as td:
            apk = os.path.join(td, "wrongabi.apk")
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr("lib/x86_64/libexample.so", make_elf64())
            results, count = inspect_apk(apk, "arm64-v8a")
            self.assertEqual(count, 1)
            self.assertTrue(any(errors for _, errors in results))

    def test_accepts_valid_p4a_pybundle_archive(self):
        with tempfile.TemporaryDirectory() as td:
            apk = os.path.join(td, "pybundle.apk")
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr("lib/arm64-v8a/libvalid.so", make_elf64())
                archive.writestr("lib/arm64-v8a/libpybundle.so", b"\x1f\x8b\x08\x08" + b"\x00" * 20)
            results, count = inspect_apk(apk, "arm64-v8a")
            self.assertEqual(count, 2)
            self.assertFalse(any(errors for _, errors in results))

    def test_rejects_corrupted_p4a_pybundle_archive(self):
        with tempfile.TemporaryDirectory() as td:
            apk = os.path.join(td, "pybundle_corrupted.apk")
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr("lib/arm64-v8a/libvalid.so", make_elf64())
                archive.writestr("lib/arm64-v8a/libpybundle.so", b"corrupted")
            results, count = inspect_apk(apk, "arm64-v8a")
            self.assertEqual(count, 2)
            by_name = {name: errors for name, errors in results}
            self.assertTrue(by_name["lib/arm64-v8a/libpybundle.so"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
