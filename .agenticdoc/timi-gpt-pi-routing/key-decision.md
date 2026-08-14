# KDR: timi-gpt-pi-routing

## R (Requirements)

- Keep one built-in Pi provider ID, `timi`.
- Select the wire protocol by model family.
- Preserve standalone Codex's user-level TiMiAIHub integration.
- Include managed-child health detection in Multi-Workers.
- Build the linked Pi runtime after verification.

## A (Architecture)

- D-001: Use a mixed-API `timi` provider; reject separate provider IDs and sharing Codex's local sanitizer.
- D-002: Treat Pi and Codex as separate launcher integration boundaries.
- D-003: Make the `mw serve` parent supervise child liveness and fail closed.
- D-004: User explicitly approved running `npm run build` after tests and `npm run check` on 2026-08-14.

## I (Implementation)

- Pending implementation plan.
