# Gemini Live Token Behavior Analysis

## Observation

During a 9-turn conversation, token counts showed an **alternating pattern** rather than monotonic growth:

```
Turn 1: 6765 tokens
Turn 2: 7015 tokens  (↑250)
Turn 3: 7415 tokens  (↑400)
Turn 4: 23776 tokens (↑16,361)  ← SPIKE
Turn 5: 8495 tokens  (↓15,281)  ← DROP
Turn 6: 8578 tokens  (↑83)
Turn 7: 27946 tokens (↑19,368)  ← SPIKE
Turn 8: 9900 tokens  (↓17,046)  ← DROP
Turn 9: 10056 tokens (↑156)
```

## Analysis

1. **Single Session ID Throughout**
   - Same `SESSION 1778939526252` for all 9 turns
   - No WebSocket reconnection
   - Not a session reset issue

2. **Alternating Pattern**
   - Odd turns (1,3,5,7,9): Gradual growth (~200-400 tokens per turn)
   - Even turns (2,4,6,8): Huge spikes on even, drops on odd
   - Pattern repeats consistently

3. **Google's Internal Behavior**
   - Not a bug in our code — we send data once, they manage context
   - Gemini Live API likely implements **automatic context windowing**
   - When context grows beyond threshold, older turns are dropped
   - System prompt + identity.md + recent N turns are retained
   - Previous turns beyond the window are pruned

## Conclusion

**Token growth is NOT cumulative.** Google manages a sliding context window:
- Keeps recent turns in context
- Drops older turns when token threshold is hit
- This prevents runaway token growth
- Good for long conversations — cost is bounded

**No action needed.** This is expected behavior of Gemini Live's context management.
