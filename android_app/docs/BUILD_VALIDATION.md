# Android Build Validation

This project targets Android API 36 and configures Android NDK r28c (`28.2.13676358`). NDK r28 enables 16 KB ELF segment alignment by default, but packaged/prebuilt native libraries must still be inspected individually.

## Run source regression tests

From the repository root, install the declared dependencies and run the suite:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p 'test_*.py' -v
```

Two live-network integration tests are skipped by default. Their skipped status is reported separately from passed tests.

## Validate a built APK

After producing an APK in `bin/`, run the same strict native-library checker used by CI:

```bash
python tools/check_elf_alignment.py bin/your-app.apk --abi arm64-v8a
```

The check fails if the APK cannot be opened, contains no native `.so` libraries, includes malformed or unexpected-architecture ELF libraries, or has any loadable ELF segment that does not satisfy the 16 KB alignment checks.

The GitHub Actions workflow additionally checks APK ZIP alignment, package identity, target SDK, debuggable status, APK signature, and the independently configured trusted release-certificate fingerprint before publishing a production release.

## Important limitations

Passing source tests and APK structural checks does not prove that the application works on every Android device or that Google Play Protect will accept it. Install and test the actual APK on an Android emulator or physical device, including download destinations, opening downloaded files, and SAF folder access. Investigate any remaining Play Protect warning using the actual APK and the exact warning text; do not disable Play Protect as a workaround.
