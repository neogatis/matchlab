# Phase 19 — Push notifications

## Goal

Add privacy-preserving push delivery for the notification types already created by MatchLab, especially mutual matches and chat messages.

The product specification requires push notifications and unread chat state. Unread already exists in Phase 11; this phase adds the push delivery path.

## Device registration

Push devices are stored separately from users.

Each device stores:
- user id;
- provider: APNS or FCM;
- platform: IOS or ANDROID;
- SHA-256 token hash for deduplication;
- an opaque token_ref;
- locale;
- enabled state;
- last-seen timestamps.

The raw push token is not stored in PostgreSQL.

A PushTokenVault interface is responsible for storing and resolving the token outside the application database.

## Delivery outbox

push_deliveries is an idempotent outbox keyed by:
- notification_id;
- device_id.

States:
- PENDING
- SENDING
- SENT
- FAILED
- DISABLED

Transient failures are retried with bounded backoff. Invalid device tokens disable the device instead of retrying forever.

## Privacy

Push message bodies are deliberately generic.

For MESSAGE notifications, the actual chat message text is never placed into the push payload.

Examples:
- MATCH: “У вас взаимный интерес”
- MESSAGE: “У вас новое сообщение”

This limits sensitive content exposure on locked screens and provider logs.

## Integration

Phase 10 mutual-match notifications and Phase 11 message notifications now enqueue push deliveries automatically after the in-app notification row is created.

If a user has no registered device, no delivery row is created and the in-app notification still works normally.

## Providers

The service exposes a PushProviderClient interface.

Real APNs/FCM clients require deployment credentials and provider configuration. Those credentials are not committed to the repository.

CI uses fake provider clients to validate:
- success;
- invalid-token handling;
- retry behavior;
- payload privacy;
- idempotency.

## Known deployment dependency

A production PushTokenVault implementation and APNs/FCM credentials must be configured before real mobile push can leave the server. The database/outbox and application hooks are ready.
