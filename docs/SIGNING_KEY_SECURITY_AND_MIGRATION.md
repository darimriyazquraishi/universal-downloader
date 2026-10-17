# Android Release Signing Security & Key Migration Guide

## 1. Independent Trusted Signing Fingerprint Requirement

In production CI/CD workflows (`.github/workflows/build_apk.yml`), establishing cryptographic trust cannot rely solely on the supplied release keystore validating against itself. If an attacker or untrusted party provides an arbitrary valid keystore, verifying the keystore against itself will always succeed while silently replacing the application's genuine signing identity.

To prevent this supply-chain risk:

1. **Mandatory Secret**: `RELEASE_CERT_SHA256` is mandatory for all production release builds. If missing, empty, or improperly formatted, the workflow fails safely immediately without producing a release.
2. **Strict Hex Normalization**: The trusted fingerprint secret is validated and normalized by stripping all colons, spaces, and whitespace and converting to lowercase 64-character hexadecimal (`^[0-9a-f]{64}$`).
3. **Independent Trust Verification**: After Buildozer and `apksigner` sign the APK, the APK's actual signer certificate SHA-256 fingerprint (`ACTUAL_CERT_FP`) is extracted and verified against `RELEASE_CERT_SHA256`. Both `ACTUAL_CERT_FP` and the supplied keystore certificate (`EXPECTED_KS_FP`) must match the independent trusted value.
4. **Debug Identity Rejection**: Signatures containing `CN=Android Debug` or `O=Android` are strictly rejected.
5. **Modern Signature Schemes**: Modern Android requires APK Signature Scheme v2 or v3; v1-only signatures are rejected.

---

## 2. Key Migration Implications (Compromised Signing Key)

If a release signing key is ever compromised, leaked, or corrupted, the following migration rules apply depending on distribution channel:

### Direct APK Distribution / Sideloading

1. **Android Package Signature Incompatibility**:
   Android's package manager strictly enforces that updates to an existing installed application must be signed with the identical cryptographic key (`INSTALL_FAILED_UPDATE_INCOMPATIBLE`).
   - If the key is changed without a migration lineage, users attempting to install the updated APK over the previous version will encounter an install error.
   - Users must uninstall the old version before installing the APK signed with the new key, which removes app-specific private data (though files saved to public MediaStore Downloads remain accessible).

2. **Key Rotation via APK Signature Scheme v3 Lineage**:
   Android 9.0 (API 28) and higher supports APK Signature Scheme v3 with **key rotation lineage**:
   - Create a signing lineage file using `apksigner rotate`:
     ```bash
     apksigner rotate \
       --out /path/to/signing_lineage.bin \
       --old-signer --ks old_compromised.keystore --ks-key-alias old_alias \
       --new-signer --ks new_secure.keystore --ks-key-alias new_alias
     ```
   - Sign the APK using both the new key and the lineage:
     ```bash
     apksigner sign \
       --ks new_secure.keystore \
       --ks-key-alias new_alias \
       --lineage /path/to/signing_lineage.bin \
       UniversalDownloader-v2.0.0.apk
     ```
   - Android 9+ devices recognize the cryptographic lineage and permit seamless in-place updates.
   - For devices running Android 8.1 or earlier, the app must fall back to the v1/v2 signature or require a clean reinstall.

### Google Play Store (If Distributed via Play Console)

1. **Google Play App Signing (Play Feature)**:
   - If Play App Signing is enabled, Google manages the final app delivery key while developers hold the upload key.
   - If an upload key is compromised, request an **Upload Key Reset** directly in the Google Play Console under **Setup > App Integrity > Request upload key reset**.
   - If the app signing key itself was compromised, Google Play allows requesting an app signing key upgrade for new installs and supported devices.

### Immediate Containment Steps

1. Immediately invalidate and remove the old secrets (`RELEASE_KEYSTORE_BASE64`, `RELEASE_KEYSTORE_PASSWD`, `RELEASE_KEYALIAS_PASSWD`) from GitHub repository secrets.
2. Generate a new 4096-bit RSA or EC P-256 production keystore in an offline, air-gapped environment.
3. Compute the new SHA-256 fingerprint:
   ```bash
   keytool -exportcert -alias "<alias>" -keystore release.keystore | sha256sum | awk '{print $1}'
   ```
4. Set the new fingerprint as `RELEASE_CERT_SHA256` in GitHub repository secrets.
5. Publish a security advisory and notify users with clear instructions on upgrading.
