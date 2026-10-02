# Phase 11 — Chat

## Goal

Allow direct text chat only after a mutual MatchLab match exists.

Phase 10 creates the mutual match. Phase 11 creates or opens the conversation and handles messages.

## Access rule

A conversation can exist only for a row in `matches`.

Only the two users stored on that match can:
- open/create the conversation;
- read its messages;
- send messages;
- mark incoming messages read.

A unilateral interest never creates a conversation.

## MVP message type

Only text messages are enabled in this phase.

Photo messages remain intentionally deferred, matching the product specification.

Text validation:
- whitespace-only messages are rejected;
- maximum length is 4,000 characters;
- the database enforces the same constraint.

## Idempotency

Clients may provide `client_message_id`.

The tuple:
`conversation_id + sender + client_message_id`
is unique.

A retry with the same id returns the original message instead of creating a duplicate notification or analytics event.

## Unread

Unread is based on `messages.read_at`.

Reading a conversation marks only messages sent by the other participant. The user's own messages are never marked read by that action.

## Blocking

Existing history remains readable after a block, but neither participant can send another message while either directional block exists.

This supports safety without silently deleting evidence/history.

## Notifications

A successful new text message creates:
- a generic in-app MESSAGE notification for the recipient;
- a MESSAGE_SENT product event.

The notification and event do not contain the private message body.

Push delivery itself remains Phase 19.

## Pagination

Messages are returned newest-window first internally and then presented chronologically. Cursoring uses `before_id`.

Default message page size: 50.
Maximum: 100.

## Conversation list

The service exposes:
- match id;
- other user id/display name;
- last message;
- unread count;
- whether sending is currently allowed.

## Safety / reporting

Message reporting is already represented in the database by `reports.message_id`, but report workflows and moderation are Phase 12.
