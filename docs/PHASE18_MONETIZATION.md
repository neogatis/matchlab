# Phase 18 — Monetization foundation

## Goal

Prepare MatchLab for FREE / PREMIUM / PREMIUM_PLUS and one-time purchases without aggressively paywalling the MVP.

The current matching, questionnaire and messaging core remain available to FREE users. Phase 18 creates billing state and entitlements; it does not insert paywalls into current product flows.

## Plans

Logical tiers:
- FREE
- PREMIUM
- PREMIUM_PLUS

Architecture-level feature candidates from the product specification include additional active selections, extended preferences, deep compatibility breakdown, priority matching and AI relationship analysis. Their presence in billing metadata does not mean each feature is already shipped.

## Providers

Supported provider identifiers:
- APPLE
- GOOGLE
- WEB
- MANUAL

Supported environments:
- PRODUCTION
- SANDBOX

Billing mutations are designed for already verified server/store events. Raw client claims must not directly grant paid access.

## Subscriptions

The subscriptions table stores provider subscription id, product code, internal tier, status, environment, renewal state, current period and verification timestamp.

Provider plus provider subscription id is unique, making store notification retries idempotent.

Only ACTIVE or GRACE subscriptions inside their valid period produce a paid plan.

## Payments

The payments table stores verified provider transaction ids, product code, purchase kind, amount metadata, currency, status and purchase timestamp.

Provider plus provider transaction id is unique.

## One-time purchase

The architecture supports a scoped DEEP_COMPATIBILITY_REPORT entitlement.

Example scope: match:42.

A report purchase for one match does not automatically unlock reports for other matches.

## Entitlements

user_entitlements stores scoped one-time or future explicit entitlements with optional expiry and revocation.

Subscription-plan features are derived from the active plan. One-time purchases use explicit entitlements.

## Analytics

The first verified ACTIVE/GRACE subscription produces the existing SUBSCRIPTION_STARTED conversion event.

## Store readiness

This phase provides the durable schema and idempotent application boundary needed for later App Store and Google Play server-notification integrations.

Store verification itself is intentionally not faked in this phase.

## MVP paywall stance

Core matching, questionnaire and messaging remain in the FREE feature set. Phase 18 prepares monetization architecture without aggressively closing the initial MVP behind payment.
