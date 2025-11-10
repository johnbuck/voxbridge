# Inline Speech Bubble Enhancement Plan

**Branch**: `feature/inline-speech-bubble`
**Created**: 2025-11-10
**Status**: Planning Phase

## Overview

Transform the VoxBridge listening experience from a floating indicator at the top of the conversation to an inline speech bubble that becomes part of the conversation flow. This enhancement creates a seamless, Discord-like UX where user transcripts appear as speech bubbles that smoothly transition from partial to final state without causing visual jumps or disappearing elements.

## User Requirements (Confirmed via Q&A)

1. **Bubble Appearance**: Immediately when `partial_transcript` event fires (when user starts speaking)
2. **Content Display**: Show bouncing dots + streaming partial transcript text together
3. **Transition Behavior**: Keep dots and text visible together as transcript updates
4. **Finalization**: No visual change when transcript finalizes - seamless transition
5. **Timer**: Remove recording duration timer completely
6. **Mic Icon**: Remove microphone icon
7. **Scroll Position**: Bubble appears at TOP of conversation (reverse chronological order maintained)
8. **Critical**: Bubble MUST NOT disappear or cause conversation jumps during database saves

## Current Implementation Analysis

### Existing Components to Modify/Remove

1. **STTWaitingIndicator** (`frontend/src/components/STTWaitingIndicator.tsx`)
   - Currently shows: Mic icon, "Listening..." text, timer, partial transcript
   - **Action**: Remove this component entirely from VoxbridgePage
   - **Location**: Lines 1530-1536 in VoxbridgePage.tsx

2. **Message Rendering** (`frontend/src/pages/VoxbridgePage.tsx`, lines 1561-1644)
   - Already supports optimistic messages with `isPending` and `isFinalizing` flags
   - User messages display on left side with primary color theme
   - Finalizing indicator shows bouncing dots (lines 1607-1616)
   - **Action**: Extend to support "streaming transcript" state

### Existing State Management

**Current Flow** (lines 310-360 in VoxbridgePage.tsx):

```
partial_transcript event
  → setVoicePartialTranscript(text)  [line 320]
  → setIsListening(true)              [line 321]
  → setPendingUserTranscript({ text, isFinalizing: false })  [line 325]

final_transcript event
  → setVoicePartialTranscript(null)   [line 333]
  → setIsListening(false)             [line 334]
  → setPendingUserTranscript({ text, isFinalizing: true })  [line 341]
  → queryClient.invalidateQueries(['messages'])  [line 352]
```

**Key Insight**: The `pendingUserTranscript` state already creates an optimistic message placeholder. We just need to modify its rendering to include bouncing dots + streaming text.

### Auto-Clear Safety Net

**Lines 265-276**: Auto-clears `pendingUserTranscript` when matching message appears in database
```typescript
useEffect(() => {
  if (pendingUserTranscript && messages.some(m => m.content === pendingUserTranscript.text)) {
    setPendingUserTranscript(null);
  }
}, [messages, pendingUserTranscript]);
```

**Critical for seamless transition**: This ensures no duplicates when DB message arrives.

## Technical Design

### Phase 1: State Structure Enhancement

**Add new state variable** to track streaming status:

```typescript
const [isStreamingTranscript, setIsStreamingTranscript] = useState(false);
```

**Modify WebSocket event handlers**:

```typescript
// partial_transcript event handler (line 318-327)
case 'partial_transcript':
  setVoicePartialTranscript(eventData.text);
  setIsListening(true);
  setIsStreamingTranscript(true);  // NEW
  setPendingUserTranscript({
    text: eventData.text,
    isFinalizing: false,
    isStreaming: true  // NEW flag
  });
  break;

// final_transcript event handler (line 331-360)
case 'final_transcript':
  setVoicePartialTranscript(null);
  setIsListening(false);
  setIsStreamingTranscript(false);  // NEW
  setPendingUserTranscript({
    text: eventData.text,
    isFinalizing: true,
    isStreaming: false  // NEW flag
  });
  queryClient.invalidateQueries(['messages']);
  // ... rest of existing logic
  break;
```

### Phase 2: Message Rendering Enhancement

**Modify user message rendering** (around lines 1561-1644):

**Current rendering logic**:
- Shows "finalizing..." bouncing dots when `msg.isFinalizing === true`
- Shows normal content otherwise

**New rendering logic**:
- Show bouncing dots + streaming text when `msg.isStreaming === true`
- Show bouncing dots only when `msg.isFinalizing === true`
- Show normal content when both flags are false

**Proposed structure**:

```tsx
{msg.role === 'user' && (
  <div className="flex items-start space-x-2">
    <div className={`message-bubble user-message ${
      msg.isStreaming || msg.isFinalizing ? 'opacity-100' : 'opacity-100'
    }`}>
      {/* Streaming state: Show dots + text */}
      {msg.isStreaming && (
        <div className="streaming-transcript">
          <div className="flex items-center gap-2">
            <BouncingDots size="sm" />
            <span className="text-sm opacity-75">
              {msg.content || 'Listening...'}
            </span>
          </div>
        </div>
      )}

      {/* Finalizing state: Show dots only (existing behavior) */}
      {msg.isFinalizing && !msg.isStreaming && (
        <div className="flex items-center gap-2">
          <BouncingDots size="sm" />
          <span className="text-sm opacity-75">Finalizing...</span>
        </div>
      )}

      {/* Final state: Show content (existing behavior) */}
      {!msg.isStreaming && !msg.isFinalizing && (
        <div className="message-content">
          {msg.content}
        </div>
      )}

      {/* Metadata (timestamp, latency) */}
      {/* ... existing metadata rendering ... */}
    </div>
  </div>
)}
```

### Phase 3: Remove STTWaitingIndicator

**Delete or comment out**:
- Lines 1530-1536 in VoxbridgePage.tsx (STTWaitingIndicator rendering)
- Optionally: Delete `frontend/src/components/STTWaitingIndicator.tsx` entirely

**Update conditional logic**:
- Remove `isListening` check from conversation area
- Rely entirely on inline speech bubble

### Phase 4: Create BouncingDots Component

**New component** (`frontend/src/components/BouncingDots.tsx`):

```tsx
interface BouncingDotsProps {
  size?: 'sm' | 'md' | 'lg';
  color?: string;
}

export const BouncingDots: React.FC<BouncingDotsProps> = ({
  size = 'md',
  color = 'currentColor'
}) => {
  const sizeClasses = {
    sm: 'w-1.5 h-1.5',
    md: 'w-2 h-2',
    lg: 'w-3 h-3'
  };

  return (
    <div className="flex items-center gap-1">
      <div className={`${sizeClasses[size]} rounded-full bg-${color} animate-bounce`}
           style={{ animationDelay: '0ms', animationDuration: '1s' }} />
      <div className={`${sizeClasses[size]} rounded-full bg-${color} animate-bounce`}
           style={{ animationDelay: '150ms', animationDuration: '1s' }} />
      <div className={`${sizeClasses[size]} rounded-full bg-${color} animate-bounce`}
           style={{ animationDelay: '300ms', animationDuration: '1s' }} />
    </div>
  );
};
```

**Reuse existing bounce animation** from TailwindCSS or existing styles.

### Phase 5: Seamless Transition Logic

**Ensure no visual jumps during transitions**:

1. **Partial → Final Transition** (same bubble, different content):
   - Bubble stays in place
   - Dots remain visible
   - Text updates from partial to final
   - `isStreaming: true` → `isFinalizing: true`
   - No position change, no re-mount

2. **Final → Database Transition** (optimistic → real):
   - Auto-clear effect (lines 265-276) removes `pendingUserTranscript`
   - Database query returns message with matching content
   - React re-renders with database message
   - **Key**: Same content text ensures no visual flicker
   - **Key**: Position in list maintained (newest at top)

3. **Prevent Duplicates**:
   - Content-based matching in auto-clear effect
   - Query invalidation only after final_transcript
   - `staleTime: Infinity` prevents unwanted refetches

## Implementation Steps

### Step 1: Create BouncingDots Component
- **File**: `frontend/src/components/BouncingDots.tsx`
- **Lines**: ~40 lines
- **Dependencies**: None (pure CSS animations)
- **Testing**: Visual inspection, storybook (optional)

### Step 2: Extend Message Interface
- **File**: `frontend/src/types/webrtc.ts` or inline in VoxbridgePage
- **Change**: Add `isStreaming?: boolean` to Message interface
- **Impact**: TypeScript compilation (zero runtime impact)

### Step 3: Update WebSocket Event Handlers
- **File**: `frontend/src/pages/VoxbridgePage.tsx`
- **Lines**: 318-360 (partial_transcript and final_transcript handlers)
- **Changes**:
  - Add `setIsStreamingTranscript` state variable
  - Set `isStreaming: true` in partial_transcript handler
  - Set `isStreaming: false` in final_transcript handler
- **Testing**: Manual WebRTC voice chat testing

### Step 4: Modify User Message Rendering
- **File**: `frontend/src/pages/VoxbridgePage.tsx`
- **Lines**: 1561-1644 (message rendering logic)
- **Changes**:
  - Add conditional rendering for `msg.isStreaming`
  - Integrate BouncingDots component
  - Show dots + streaming text together
  - Preserve existing finalizing and normal states
- **Testing**: Visual inspection with live transcripts

### Step 5: Remove STTWaitingIndicator
- **File**: `frontend/src/pages/VoxbridgePage.tsx`
- **Lines**: 1530-1536
- **Changes**: Delete/comment out STTWaitingIndicator rendering
- **Optional**: Delete `frontend/src/components/STTWaitingIndicator.tsx`
- **Testing**: Verify no regressions, no floating indicator

### Step 6: End-to-End Testing
- **Scenarios**:
  1. Start speaking → verify bubble appears at top with dots
  2. Continue speaking → verify partial transcript updates in place
  3. Stop speaking → verify seamless transition to final transcript
  4. Database save → verify no duplicates, no position jumps
  5. Multiple turns → verify conversation flows naturally
  6. Concurrent Discord + WebRTC → verify isolation
- **Edge Cases**:
  - Very short utterances (< 500ms)
  - Empty partial transcripts
  - Network delays during finalization
  - Rapid consecutive messages

## Visual Design Specifications

### Speech Bubble Styling

**User Message Bubble** (existing styles from VoxbridgePage.tsx):
- Background: Primary color (`bg-primary-500/20` or similar)
- Border: Subtle border (`border border-primary-500/30`)
- Padding: `p-3` or `p-4`
- Border radius: `rounded-lg`
- Text color: Primary text (`text-primary-900`)

**Streaming State Additions**:
- Bouncing dots: Small size (`w-1.5 h-1.5`)
- Dots color: Match text color or slightly muted
- Layout: Horizontal flex with gap (`flex items-center gap-2`)
- Text opacity: `opacity-75` for streaming text (to indicate in-progress)

**Transition Animations**:
- No animations needed (per user requirements - seamless, no visual change)
- Exception: Bouncing dots continue throughout partial → final transition

### Layout Positioning

**Conversation Flow**:
```
┌────────────────────────────────────────┐
│  [Audio Controls]  [Connect Button]   │  ← Top controls
├────────────────────────────────────────┤
│                                        │
│  ┌──────────────────────────┐         │  ← User bubble (newest)
│  │ ● ● ● "Hello, I need..." │         │     Bouncing dots + text
│  └──────────────────────────┘         │
│                                        │
│         ┌─────────────────────────┐   │  ← Assistant bubble
│         │ "How can I help you?"   │   │
│         └─────────────────────────┘   │
│                                        │
│  ┌──────────────────────────┐         │  ← Previous user bubble
│  │ "What time is it?"       │         │
│  └──────────────────────────┘         │
│                                        │
└────────────────────────────────────────┘
```

**Reverse Chronological Order** (newest at top, per current implementation):
- User speech bubble appears at position [0] in messages array
- Auto-scroll NOT needed (bubble is already at top)
- Existing scroll behavior maintained

## Files to Modify

### New Files
1. `frontend/src/components/BouncingDots.tsx` (~40 lines)

### Modified Files
1. `frontend/src/pages/VoxbridgePage.tsx`
   - Line 293-360: WebSocket event handlers (add `isStreaming` flag)
   - Line 1530-1536: Remove STTWaitingIndicator rendering
   - Line 1561-1644: Update user message rendering logic
   - Add `isStreamingTranscript` state variable

2. `frontend/src/types/webrtc.ts` (or inline types)
   - Add `isStreaming?: boolean` to Message interface

### Deleted Files (Optional)
1. `frontend/src/components/STTWaitingIndicator.tsx` (if no longer needed elsewhere)

## Testing Strategy

### Unit Tests (Optional)
- BouncingDots component rendering
- Message interface TypeScript validation

### Integration Tests
- WebSocket event → state update flow
- Optimistic message creation/update/deletion
- Auto-clear effect with content matching

### Manual E2E Testing (Critical)
1. **Partial Transcript Flow**:
   - Start speaking in browser
   - Verify bubble appears at top immediately
   - Verify bouncing dots visible
   - Verify partial transcript text updates in real-time
   - Verify no floating "Listening" component

2. **Final Transcript Flow**:
   - Stop speaking
   - Verify seamless transition (no visual jump)
   - Verify text finalizes in same bubble
   - Verify database save completes
   - Verify no duplicate messages

3. **Multi-Turn Conversation**:
   - Speak → AI responds → Speak again
   - Verify conversation builds naturally
   - Verify scroll position maintained
   - Verify no orphaned bubbles

4. **Edge Cases**:
   - Very short utterances (1-2 words)
   - Long utterances (30+ seconds)
   - Rapid consecutive messages
   - Network interruption during finalization

## Success Criteria

### Functional Requirements
- ✅ Speech bubble appears at top of conversation when user starts speaking
- ✅ Bouncing dots + streaming transcript text visible together
- ✅ Seamless transition from partial → final → database (no jumps)
- ✅ No floating "Listening" indicator at top
- ✅ No recording timer visible
- ✅ No microphone icon visible
- ✅ Bubble never disappears or gets destroyed
- ✅ Content updates in place without re-mounting

### Performance Requirements
- ✅ No noticeable lag when bubble appears
- ✅ Smooth text updates as partial transcripts stream
- ✅ No frame drops during bouncing dot animation
- ✅ Database transition completes within 500ms

### UX Requirements
- ✅ Conversation feels natural and Discord-like
- ✅ No visual glitches or flickers
- ✅ User can see their words appearing in real-time
- ✅ Clear visual feedback that system is listening
- ✅ No confusion about message state

## Risks and Mitigations

### Risk 1: Visual Jumps During Database Transition
**Probability**: Medium
**Impact**: High (violates core requirement)
**Mitigation**:
- Use content-based matching for auto-clear effect
- Ensure React key stability (use content hash if needed)
- Test thoroughly with various transcript lengths
- Add defensive logging to catch edge cases

### Risk 2: Duplicate Messages
**Probability**: Low
**Impact**: Medium
**Mitigation**:
- Existing auto-clear effect (lines 265-276) handles this
- Content-based deduplication
- `staleTime: Infinity` prevents unwanted refetches
- Manual testing of rapid consecutive messages

### Risk 3: Bouncing Dots Performance
**Probability**: Low
**Impact**: Low
**Mitigation**:
- Use CSS animations (GPU-accelerated)
- Small dot size (minimal DOM impact)
- Reuse existing Tailwind bounce animation
- Test on low-end devices if available

### Risk 4: Scroll Behavior Regression
**Probability**: Low
**Impact**: Medium
**Mitigation**:
- No changes to scroll logic needed (bubble at top)
- Verify scroll position maintained during testing
- Test with long conversation histories

## Rollback Plan

If critical issues arise:

1. **Immediate Rollback** (restore STTWaitingIndicator):
   - Revert commit(s) on feature branch
   - Or: Re-enable STTWaitingIndicator rendering
   - Comment out new inline bubble logic

2. **Partial Rollback** (hybrid approach):
   - Keep STTWaitingIndicator as fallback
   - Add feature flag to toggle behavior
   - Gather user feedback before full deployment

3. **Debug-In-Place**:
   - Add verbose logging to state transitions
   - Check browser console for React warnings
   - Inspect WebSocket event timing
   - Review auto-clear effect execution

## Timeline Estimate

**Total Effort**: ~4-6 hours

- **Step 1 (BouncingDots)**: 30 minutes
- **Step 2 (Type updates)**: 15 minutes
- **Step 3 (Event handlers)**: 30 minutes
- **Step 4 (Message rendering)**: 1-2 hours (most complex)
- **Step 5 (Remove STTWaitingIndicator)**: 15 minutes
- **Step 6 (E2E testing)**: 1-2 hours
- **Documentation/cleanup**: 30 minutes

## Future Enhancements (Out of Scope)

- Typing indicators for assistant responses
- User avatar/icon in speech bubbles
- Swipe-to-delete gestures
- Edit transcript after finalization
- Voice activity visualization (waveform)
- Different bubble styles per agent
- Accessibility improvements (ARIA labels, screen reader support)

## References

### Existing Code
- `frontend/src/pages/VoxbridgePage.tsx` (1,600+ lines)
- `frontend/src/components/STTWaitingIndicator.tsx` (existing implementation)
- `docs/WEBRTC_FIXES_SESSION_SUMMARY.md` (WebRTC architecture)

### Related Documentation
- [CLAUDE.md](../../CLAUDE.md) - VoxBridge overview
- [AGENTS.md](../../AGENTS.md) - Comprehensive architecture
- [ARCHITECTURE.md](../../ARCHITECTURE.md) - Documentation index
- [docs/architecture/voxbridge-2.0-transformation-plan.md](../architecture/voxbridge-2.0-transformation-plan.md) - VoxBridge 2.0 plan

---

**Document Status**: ✅ Ready for Review
**Next Step**: User approval → Create branch → Begin implementation
