# Phase 27 — Phone OTP + Google + Apple authentication

## Result

MatchLab now supports one account with multiple authentication methods:

- email + password;
- phone number + SMS OTP;
- Google OpenID Connect ID token;
- Sign in with Apple ID token.

Users can also link phone/Google/Apple to an already authenticated account so authentication methods do not need to create separate profiles.

## Phone OTP flow

Public endpoints:

- `POST /api/v1/auth/phone/request`
- `POST /api/v1/auth/phone/verify`

Linking endpoints for an authenticated user:

- `POST /api/v1/auth/link/phone/request`
- `POST /api/v1/auth/link/phone/verify`

Phone numbers are normalized to E.164. OTP codes:

- are six digits;
- expire after 10 minutes;
- allow at most five verification attempts;
- are stored only as SHA-256 hashes;
- are rate-limited per phone number;
- are one-time use.

The database stores the verified E.164 number on the user and a hashed PHONE identity subject in `auth_identities`.

## SMS provider

Initial production adapter: Twilio.

Required variables:

- `SMS_PROVIDER=twilio`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- either `TWILIO_FROM_NUMBER` or `TWILIO_MESSAGING_SERVICE_SID`

No OTP value is returned from the HTTP API.

## Google / Apple flow

Public endpoints:

- `POST /api/v1/auth/oidc/nonce`
- `POST /api/v1/auth/oauth`

Authenticated linking endpoints:

- `POST /api/v1/auth/link/oidc/nonce`
- `POST /api/v1/auth/link/oauth`

The server issues a one-time nonce before native authentication. It verifies:

- provider signature against official JWKS;
- issuer;
- audience;
- expiration;
- subject;
- nonce/replay protection.

Required audiences:

- `GOOGLE_CLIENT_ID`
- `APPLE_CLIENT_ID`

Apple and Google identities are keyed by provider + immutable subject, not by display name.

## Account linking rules

If a provider identity is already linked, it always returns the same MatchLab account.

For a new social identity with a verified email:

- it may link automatically only to an existing account whose email was already verified;
- an unverified existing email does not silently merge, preventing unsafe account takeover/merge behavior.

A phone-first account can later link Google or Apple while authenticated. A Google/Apple-first account can later link a phone number.

## Current production status

The backend endpoints can be deployed independently of provider credentials.

Until real provider configuration is added:

- phone auth is present but SMS delivery is not production-enabled;
- Google backend verification is present but store/client configuration is incomplete;
- Apple backend verification is present but store/client configuration is incomplete.

Store-readiness flags for Google Sign-In and Sign in with Apple therefore remain fail-closed.

## Next

1. add SMS provider credentials and run a real phone OTP smoke test;
2. create Google OAuth client IDs and add the native client ID to Railway;
3. create the Apple App ID / Sign in with Apple capability and configure the audience;
4. build native iOS/Android auth screens;
5. run provider-specific production login/link tests;
6. only then mark Apple/Google production readiness true.
