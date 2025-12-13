# Duty Swap Feature - User Guide

## Accessing the Duty Swap System

The duty swap feature is now integrated into the duty calendar interface with three main access points:

### 1. **Calendar Header Navigation** (Always Visible)
Located at the top of the duty calendar, you'll see two buttons:
- **"My Swap Requests"** - View and manage your swap requests
- **"Help Others"** - Browse open requests where you can help

### 2. **Calendar Day Modal** (When Viewing a Duty Day)
Click on any day in the calendar to open the day detail modal. If you're assigned a duty role on that day, you'll see:
- **"Request [Role] Swap"** buttons for each role you're assigned
- Example: "Request Instructor Swap", "Request Tow Pilot Swap", etc.
- These buttons only appear if:
  - You're assigned that role on that day
  - The role is scheduled (configured in site settings)
  - The day is in the future

### 3. **Direct URL Access**
You can also bookmark these URLs:
- My Requests: `/duty/swap/my-requests/`
- Open Requests: `/duty/swap/open-requests/`

---

## How to Request Coverage for Your Duty

### Step 1: Find Your Assigned Duty
1. Go to the Duty Roster Calendar
2. Click on the day you're scheduled for duty
3. Verify you're listed for a role (e.g., "Instructor: Your Name")

### Step 2: Create a Swap Request
1. Click the **"Request [Your Role] Swap"** button in the modal
2. Fill out the request form:
   - **Request Type:**
     - **General Broadcast**: Send to all eligible members for that role
     - **Direct Request**: Send to a specific member only
   - **Notes**: Explain why you need coverage (e.g., "Family wedding")
   - **Emergency**: Check if duty is less than 48 hours away

### Step 3: Wait for Offers
- Eligible members will receive email notifications
- You'll receive emails when offers come in
- Check **"My Swap Requests"** to see all offers

### Step 4: Review and Accept an Offer
When someone makes an offer, they choose:
- **Swap**: "I'll take your date if you take my [proposed date]"
- **Cover**: "I'll just take your date, no swap needed"

To accept:
1. Go to **"My Swap Requests"**
2. Click **"View Details"** on the request
3. Review all offers
4. Click **"Accept"** on the offer you want
5. Other offers are auto-declined
6. Duty calendar is updated automatically

---

## How to Help Others (Make an Offer)

### Step 1: Browse Open Requests
1. Click **"Help Others"** in the calendar header
2. See all open requests for roles you're qualified for
3. Requests marked **URGENT** need help within 48 hours

### Step 2: Make an Offer
1. Click **"Make Offer"** on a request
2. Choose your offer type:
   - **Cover**: Just take their duty, no swap needed
   - **Swap**: Take their duty if they take one of your scheduled duties
3. If swapping, select which of your duty dates you propose
4. Add optional notes
5. Submit your offer

### Step 3: Wait for Response
- The requester will review your offer
- You'll receive an email when they accept or decline
- Check **"My Swap Requests"** to see your pending offers

---

## Request Types Explained

### General Broadcast
- Sent to **all** eligible members for that role
- Anyone qualified can make an offer
- Best for maximum visibility

### Direct Request
- Sent to **one specific member** only
- If they decline, you can convert to General Broadcast
- Best when you already know someone who can help

---

## Offer Types Explained

### Cover (No Swap)
- You take their duty, they owe you nothing
- Simple and generous
- No blackout date checking needed

### Swap (Exchange Duties)
- You take their duty on Date A
- They take your duty on Date B
- System checks if Date B is in their blackout period
- ⚠️ **Warning shown** if proposed date conflicts with their blackouts
- They can still accept despite the warning

---

## Time-based Urgency

The system tracks how soon the duty is:
- **>14 days**: Normal priority
- **8-14 days**: "Soon" - reminder emails sent
- **3-7 days**: "Urgent" - highlighted in interface
- **<3 days**: "Emergency" - auto-escalated to Duty Officer

### Critical Roles (Tow Pilot, Duty Officer)
If no coverage is found <24 hours before duty:
- Duty Officer is notified automatically
- Operations **MUST** be cancelled (no tow pilot = can't fly, no DO = no one in charge)
- All members notified of cancellation

### Optional Roles (Instructor, Assistant DO)
If no coverage is found:
- Operations can proceed without the role
- Or Duty Officer can manually assign someone
- Or Duty Officer can cancel operations

---

## Site Configuration Requirements

**IMPORTANT**: Swap requests are only available for roles that are **scheduled ahead of time**.

Check your Site Configuration settings:
- `schedule_instructors` - Must be True to swap instructor duties
- `schedule_tow_pilots` - Must be True to swap tow pilot duties
- `schedule_duty_officers` - Must be True to swap DO duties
- `schedule_assistant_duty_officers` - Must be True to swap ADO duties

If a role is NOT scheduled (flag=False), the "Request Swap" button won't appear for that role because there's no scheduled assignment to swap.

---

## Blackout Date Protection

When someone offers a **swap** (not a cover), the system checks:
- Is the proposed swap date in the requester's blackout period?
- If YES: ⚠️ Warning shown to requester before accepting
- If NO: No warning, safe to accept

The requester can still accept despite the warning (maybe plans changed).

---

## Managing Your Requests

### Cancel a Request
1. Go to **"My Swap Requests"**
2. Click **"View Details"** on the request
3. Click **"Cancel Request"**
4. All offerers are notified

### Convert Direct to General
If your direct request is declined:
1. Go to **"My Swap Requests"**
2. Click **"View Details"** on the request
3. Click **"Broadcast to All"**
4. All eligible members are notified

### Decline an Offer
1. Go to **"My Swap Requests"**
2. Click **"View Details"** on the request
3. Click **"Decline"** next to any offer
4. That offerer is notified

---

## Email Notifications

You'll receive emails for:
- **New requests** sent to you (if you're eligible)
- **Offers made** on your requests
- **Offers accepted** by requesters
- **Offers declined** by requesters
- **Requests cancelled** by requesters
- **Emergency escalations** (if you're Duty Officer)

All emails include direct links to the relevant pages.

---

## Troubleshooting

### "Request Swap" button doesn't appear
- Check if you're actually assigned that role on that day
- Check if the role is scheduled in Site Configuration
- Check if the day is in the future (can't swap past duties)

### No offers received
- Request may be too far in future (members forget)
- Try converting to General Broadcast if it was Direct
- Check if enough members are qualified for that role
- Consider making it Emergency if time is short

### Can't see open requests
- Check if you're qualified for any scheduled roles
- Only roles you're qualified for appear in "Help Others"
- Contact admin if your role qualifications are wrong

---

## Best Practices

### For Requesters
- **Request early**: Don't wait until the last minute
- **Be specific**: Explain your conflict in the notes
- **Check blackouts**: Review proposed swap dates carefully
- **Respond promptly**: Don't leave offers pending too long

### For Offerers
- **Check your schedule**: Make sure you're really available
- **Propose good swap dates**: Avoid holidays/busy weekends
- **Add helpful notes**: Explain any conditions or flexibility
- **Be generous**: Consider "cover" offers when you can

### For Everyone
- **Keep blackouts updated**: System can only warn about dates you've marked
- **Respond to requests**: Even if you can't help, it's good to know
- **Thank helpers**: The system handles the swap, but gratitude matters
