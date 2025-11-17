# Issue #188 - Additional Workflow Clarification: Approval Decision Outcomes

## Problem Addressed

The membership workflow needed clarification on how different clubs handle the **Approval Decision** outcomes in the new member application process. Specifically:

1. **SSC Model**: "Everybody is provisional" - all approved applicants become Probationary Members
2. **Other Clubs**: May have three distinct approval outcomes with different initial statuses
3. **"Pulse and Checkbook" Clubs**: May grant immediate Full Member status to most applicants

## Changes Made

### 1. Enhanced Approval Decision Documentation

**Added New Section**: "Approval Decision Outcomes (Club-Configurable)"

**SSC Model Clarification**:
- **Approved → Probationary Status**: Everyone starts as probationary regardless of experience
- **Conditional → Probationary Status**: Same outcome with additional monitoring
- **Rejected**: Application denied
- Philosophy: "Everybody is provisional" - all new members must prove themselves

**Alternative Club Models**:
- **Less Demanding**: May grant immediate Full Member status to experienced pilots
- **"Pulse and Checkbook"**: Most applicants get immediate Full Member status with payment

### 2. Updated Status Definitions

**Enhanced Probationary Member Definition**:
- Changed from: "Full privileges under observation period"
- Changed to: "**ALL new SSC members start here** - Full privileges under observation period"

### 3. Added SSC-Specific Requirements Section

**New Section**: "SSC Probationary Member Requirements"
- Explains "everyone is provisional" philosophy
- Lists benefits of consistent evaluation approach
- Notes equal treatment regardless of experience
- Acknowledges other clubs may use different approaches

### 4. Updated Workflow Diagram

**Technical Fix**: Added missing connection in workflow diagram (Y → Z path)

## Key Benefits

1. **Clear SSC Policy**: Documents that ALL new SSC members start as probationary
2. **Multi-Club Flexibility**: Explains how other clubs might handle approvals differently
3. **Philosophy Documentation**: Captures the reasoning behind SSC's more demanding approach
4. **Implementation Guidance**: Helps other clubs understand their options

## Club Comparison Framework

| Club Type | Approval Approach | Initial Status for Approved Members |
|-----------|-------------------|-----------------------------------|
| **SSC (Demanding)** | Everyone is provisional | All → Probationary Member |
| **Moderate Clubs** | Experience-based decisions | Experienced → Full Member<br>New → Probationary Member |
| **"Pulse & Checkbook"** | Payment-based | Most → Full Member |

## Files Modified

1. **Primary Document**: `docs/workflows/12-membership-manager-workflow.md`
   - Added "Approval Decision Outcomes" section
   - Enhanced status definitions with SSC emphasis
   - Added SSC probationary requirements explanation
   - Fixed workflow diagram connection

## Technical Considerations

- No database or code changes required
- Documentation reflects operational policy differences
- System supports all described club models through flexible status assignment
- Maintains backward compatibility and multi-club applicability

## Outcome

The workflow documentation now clearly distinguishes between:
- SSC's rigorous "everyone is provisional" approach
- More permissive club models that may grant immediate full membership
- The flexibility of the system to accommodate different club philosophies

This addresses the feedback about SSC's demanding membership standards while maintaining the document's value for other clubs with different approaches.

---

*This update ensures the workflow accurately represents SSC's specific membership philosophy while remaining useful for clubs with different approval criteria.*
