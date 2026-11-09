# Viet Legends v1.7.8 – Long Vương Boss Effects

## Combat effects
- Added stage-specific cast visuals for the five Long Vương event bosses.
- Added dedicated hit feedback when the event boss is struck.
- Added dedicated player-hit feedback for direct boss attacks and damaging explosions.
- Effects are drawn with the existing Canvas renderer; no additional animation asset bundle is required.

## Dialogue responsiveness
- Added a client-side lock to prevent duplicate Continue requests.
- The Continue button immediately shows a busy state while the request is pending.
- The next dialogue line is rendered directly from the `/api/ocean/dialogue/next` response, avoiding an unnecessary follow-up GET request.
- Recoverable request errors restore the button so the player can retry.

## Cache and verification
- Bumped the service-worker cache key to `dino-v17-ocean-boss-fx-dialogue-fast`.
- JavaScript syntax check: passed.
- Python compile check for `app.py`: passed.
- Dependency-free regression checks: 10 passed.
- Full application/browser gameplay was not launched in this environment.
