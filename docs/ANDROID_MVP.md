# Android MVP

Package: `com.neogatis.matchlab`

The first Android client includes:

- phone OTP sign-in against the production MatchLab API;
- Google Credential Manager flow wired to the server OIDC nonce endpoint;
- persistent MatchLab session and CSRF cookies;
- Firebase Cloud Messaging token acquisition;
- automatic FCM device registration with `/api/v1/push/devices`;
- foreground notification display;
- CI-built debug APK.

Firebase config is based on the registered Android app in project `matchlab-255fd`.

## Debug signing

The CI debug keystore is cached under the GitHub Actions cache key:

`matchlab-android-debug-keystore-v1`

Current SHA-1:

`EF:73:1B:AF:97:46:D6:4D:D7:5C:9A:C6:9B:43:E5:B9:73:09:32:26`

This SHA-1 must be registered in the Google OAuth project as an Android OAuth client for:

- package: `com.neogatis.matchlab`
- SHA-1: the value above

The Google server client remains:

`277037547740-59d6hkkb3oht6l56htlvp1k8ep0lstnn.apps.googleusercontent.com`

## Current validation

GitHub Actions successfully builds `:app:assembleDebug`, prints the signing report, and publishes an APK artifact named:

`matchlab-android-debug`

Phone login and FCM registration can be tested before Android Google OAuth is completed. Google sign-in needs the Android OAuth client registration for the debug SHA-1.
