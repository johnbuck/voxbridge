# Conversation Flow Troubleshooting Flowchart

**VoxBridge Frontend - Quick Diagnostic Guide**

---

## Issue: "Speech Bubble Not Appearing"

```
┌─────────────────────────────────────┐
│  Speech bubble not showing?         │
└──────────────┬──────────────────────┘
               │
               ▼
    ┌──────────────────────┐
    │ Is WebSocket         │ NO ──► Check browser console
    │ connected?           │         WebSocket error?
    │ (ws:// icon)         │
    └──────┬───────────────┘
           │ YES
           ▼
    ┌──────────────────────┐
    │ Is session selected? │ NO ──► Click on a conversation
    │ (activeSessionId)    │         in the sidebar
    └──────┬───────────────┘
           │ YES
           ▼
    ┌──────────────────────┐
    │ Check DevTools:      │
    │ grep "📡" logs       │
    │ See WebSocket events?│
    └──────┬───────────────┘
           │ YES
           ▼
    ┌──────────────────────┐
    │ Check logs:          │
    │ grep "activeSessionId│ NULL ─► Stale closure bug!
    │ Is it null?          │         (Should be fixed now)
    └──────┬───────────────┘
           │ NOT NULL
           ▼
    ┌──────────────────────┐
    │ Check React Query:   │
    │ grep "🔄.*QUERY"    │
    │ Invalidation called? │ NO ──► Bug in message_saved
    └──────┬───────────────┘         handler
           │ YES
           ▼
    ┌──────────────────────┐
    │ Check cache update:  │
    │ grep "📦.*CACHE"    │
    │ Cache updated?       │ NO ──► React Query not refetching
    └──────┬───────────────┘
           │ YES
           ▼
    ┌──────────────────────┐
    │ Should work now!     │
    │ If not, check React  │
    │ DevTools Components  │
    └──────────────────────┘
```

---

## Issue: "Duplicate Speech Bubbles"

```
┌─────────────────────────────────────┐
│  Seeing duplicate messages?         │
└──────────────┬──────────────────────┘
               │
               ▼
    ┌──────────────────────┐
    │ Are both bubbles     │ NO ──► Different issue
    │ identical?           │         (check message IDs)
    └──────┬───────────────┘
           │ YES (streaming + DB)
           ▼
    ┌──────────────────────┐
    │ Check logs:          │
    │ grep "🧹.*CLEANUP"  │
    │ Chunks cleared?      │ NO ──► Bug in message_saved
    └──────┬───────────────┘         handler (line 875)
           │ YES
           ▼
    ┌──────────────────────┐
    │ Check timing:        │
    │ Cleanup BEFORE       │ NO ──► Race condition!
    │ refetch?             │         Reorder operations
    └──────┬───────────────┘
           │ YES
           ▼
    ┌──────────────────────┐
    │ Check React keys:    │
    │ DevTools → Components│
    │ Keys stable?         │ NO ──► Key changing mid-render
    └──────┬───────────────┘         (check line 1765)
           │ YES
           ▼
    ┌──────────────────────┐
    │ Check displayMessages│
    │ useMemo:             │
    │ Conditional rendering│ NO ──► Logic error in
    │ correct?             │         displayMessages (line 204)
    └──────┬───────────────┘
           │ YES
           ▼
    ┌──────────────────────┐
    │ Duplicates should    │
    │ be gone. If persists,│
    │ check dependencies   │
    │ array (line 278)     │
    └──────────────────────┘
```

---

## Issue: "AI Response Stuck in Thinking"

```
┌─────────────────────────────────────┐
│  AI thinking indicator stuck?       │
└──────────────┬──────────────────────┘
               │
               ▼
    ┌──────────────────────┐
    │ Check logs:          │
    │ grep "ai_response"   │
    │ _complete            │
    │ Event received?      │ NO ──► Check backend logs
    └──────┬───────────────┘         LLM timeout?
           │ YES
           ▼
    ┌──────────────────────┐
    │ Check logs:          │
    │ grep "💭.*THINKING" │
    │ "Complete" logged?   │ NO ──► Bug in ai_response_complete
    └──────┬───────────────┘         handler (line 850)
           │ YES
           ▼
    ┌──────────────────────┐
    │ Check state:         │
    │ setIsVoiceAI         │
    │ Generating(false)    │ NO ──► Missing state update
    │ called?              │         (line 855)
    └──────┬───────────────┘
           │ YES
           ▼
    ┌──────────────────────┐
    │ Check UI component:  │
    │ Is AIGenerating      │ YES ─► React not re-rendering
    │ Indicator still      │         (check dependencies)
    │ visible in DOM?      │
    └──────┬───────────────┘
           │ NO
           ▼
    ┌──────────────────────┐
    │ Fixed! If persists,  │
    │ check for state      │
    │ management bugs      │
    └──────────────────────┘
```

---

## Issue: "Streaming Not Working"

```
┌─────────────────────────────────────┐
│  AI response appears all at once?   │
└──────────────┬──────────────────────┘
               │
               ▼
    ┌──────────────────────┐
    │ Check logs:          │
    │ grep "ai_response"   │
    │ _chunk               │
    │ Events received?     │ NO ──► Backend not streaming
    └──────┬───────────────┘         Check backend config
           │ YES
           ▼
    ┌──────────────────────┐
    │ Check logs:          │
    │ grep "🌊.*STREAMING"│
    │ Chunks logged?       │ NO ──► Handler not processing
    └──────┬───────────────┘         chunks (line 832)
           │ YES
           ▼
    ┌──────────────────────┐
    │ Check state:         │
    │ setStreamingChunks   │ NO ──► Bug in chunk handler
    │ called?              │         (line 840)
    └──────┬───────────────┘
           │ YES
           ▼
    ┌──────────────────────┐
    │ Check displayMessages│
    │ Includes streaming   │ NO ──► Logic error in
    │ message? (line 237)  │         displayMessages
    └──────┬───────────────┘
           │ YES
           ▼
    ┌──────────────────────┐
    │ Check render logic:  │
    │ Streaming message    │ NO ──► Conditional rendering
    │ rendered with dots?  │         wrong (line 1823)
    │ (line 1823)          │
    └──────┬───────────────┘
           │ YES
           ▼
    ┌──────────────────────┐
    │ Streaming working!   │
    │ If dots missing,     │
    │ check BouncingDots   │
    │ component            │
    └──────────────────────┘
```

---

## Issue: "Message Timing Problems"

```
┌─────────────────────────────────────┐
│  Messages out of order?             │
│  Or appearing late?                 │
└──────────────┬──────────────────────┘
               │
               ▼
    ┌──────────────────────┐
    │ Check debounce:      │
    │ grep "🔄" logs      │
    │ Multiple invalidation│ YES ─► Debounce batching
    │ within 100ms?        │         (this is normal)
    └──────┬───────────────┘
           │ NO
           ▼
    ┌──────────────────────┐
    │ Check message order: │
    │ displayMessages      │
    │ .slice().reverse()   │ NO ──► Message order wrong
    │ Newest on bottom?    │         (line 1762)
    └──────┬───────────────┘
           │ YES
           ▼
    ┌──────────────────────┐
    │ Check timestamps:    │
    │ Are timestamps       │ NO ──► Clock skew between
    │ sequential?          │         frontend/backend
    └──────┬───────────────┘
           │ YES
           ▼
    ┌──────────────────────┐
    │ Check React Query:   │
    │ dataUpdatedAt        │ NO ──► Cache not updating
    │ changing?            │
    └──────┬───────────────┘
           │ YES
           ▼
    ┌──────────────────────┐
    │ Normal behavior!     │
    │ 100ms debounce adds  │
    │ slight delay (by     │
    │ design)              │
    └──────────────────────┘
```

---

## Log Grep Cheatsheet

Quick commands for troubleshooting in browser DevTools console:

```javascript
// Filter by category
console.save = () => {
  const logs = performance.getEntriesByType('console');
  console.log('Conversation flow:', logs.filter(l => /🎤|💭|🌊/.test(l)));
  console.log('WebSocket:', logs.filter(l => /📡/.test(l)));
  console.log('Cache:', logs.filter(l => /📦|🔄/.test(l)));
  console.log('Errors:', logs.filter(l => /🚨|ERROR/.test(l)));
};

// Enable verbose logging
localStorage.setItem('VITE_LOG_LEVEL', 'DEBUG');
location.reload();

// Check current state
console.log('Active Session:', window.__REACT_QUERY_STATE__);
```

---

## Critical Log Points Checklist

When troubleshooting, verify these logs exist:

- [ ] `🎤 LISTENING Started` - User starts speaking
- [ ] `📝 [PENDING_USER]` - Pending transcript set
- [ ] `💾 [DB_CONFIRMED]` - message_saved received
- [ ] `🔄 [QUERY]` - Query invalidation called
- [ ] `📦 [CACHE_UPDATED]` - Cache reflected changes
- [ ] `🧹 [AUTO_CLEAR]` - Pending transcript cleared
- [ ] `💭 THINKING Started` - AI generation started
- [ ] `🌊 [STREAMING_AI]` - Chunks received
- [ ] `🏁 [AI_COMPLETE]` - AI generation complete
- [ ] `🧹 [STREAMING_CLEANUP]` - Chunks cleared

If any are missing, that's where the bug is!

---

## State Machine Validation

```
USER MESSAGE STATES:
null → streaming → finalizing → pending → complete
  ✓      ✓           ✓          ✓         ✓

AI MESSAGE STATES:
null → thinking → streaming → complete → speaking → done
  ✓       ✓          ✓          ✓          ✓        ✓

WEBSOCKET STATES:
connecting → connected → disconnected → reconnecting
    ✓           ✓            ✓              ✓

CONVERSATION STATES:
idle → listening → processing → speaking → idle
  ✓       ✓           ✓           ✓        ✓
```

All states must transition correctly. Use logs to trace state changes!

---

## Performance Benchmarks

Expected timing for conversation turn:

```
User speaks (STT):        0-3s    🎤
Finalizing:               0.1s    ⏱️
DB save user:             0.1s    💾
AI thinking:              1-3s    💭
AI streaming:             2-5s    🌊
AI complete:              0.1s    🏁
DB save AI:               0.1s    💾
TTS playing:              2-4s    🔊
─────────────────────────────────
TOTAL:                    6-16s   ✅
```

If times are significantly longer, investigate backend performance.

---

**Related Documents:**
- [TESTING_AND_LOGGING_STRATEGY.md](TESTING_AND_LOGGING_STRATEGY.md) - Comprehensive guide
- [../../AGENTS.md](../../../AGENTS.md) - Architecture details
- [../README.md](../README.md) - Setup instructions
