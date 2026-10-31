# Hisaab: The Problem

## The Problem

**The real problem isn't record-keeping. It's getting paid without damaging the relationship.**

## What's actually going on

- **Money is stuck.** A kirana runs on thin margins and little working capital. Every ₹500 of udhaar is cash the shop can't use to restock. Late or unpaid credit is one of the biggest drains on small shops.
- **Customers are neighbors.** They are regulars, often for years. Asking "Paisa kab doge?" feels rude, and the shopkeeper fears the customer will switch to the shop next door. So many shopkeepers avoid asking, and the amount keeps growing.
- **Udhaar is also how they compete.** Offering credit keeps customers loyal, so the shopkeeper can't just stop giving it. They need a way to collect without turning it into a confrontation.
- **Follow-up is inconsistent.** The shopkeeper is busy serving customers, so reminders happen randomly, only when they remember or when the customer walks in.

## The core pain points (in order of how strongly I believe them)

1. **Recovering money without hurting the relationship.** Customers are neighbors and asking feels awkward. This is the most widely reported emotional pain.
2. **Unpredictable or delayed repayment.** Many customers pay on salary day, weekly wage day, or "when money comes," so repayment is lumpy and the shopkeeper has no clean way to track promises.
3. **Disputes and weak records.** "Maine toh de diya tha" or "Amount galat hai" happens when the record is a notebook or memory.
4. **Time.** Chasing, remembering, and calculating take attention away from serving customers.

## Context

- **Scale:** India has roughly 12 to 13 million kirana stores (commonly cited), and they still handle a large share of grocery and daily-needs retail.
- **Udhaar is normal.** Informal credit to regular customers is a standard part of kirana business, especially in neighborhoods with daily-wage or monthly-salary households.
- **Paper khata is still common.** Many shopkeepers track credit in a notebook. This led to apps like Khatabook and OkCredit, which grew fast on this exact pain point.
- **Working capital is tight.** Kirana owners often have limited access to formal bank credit, so money stuck in udhaar directly limits restocking.
- **Competition is rising.** Quick commerce (Blinkit, Zepto, Instamart), JioMart, and B2B apps put pressure on kiranas, so keeping loyal customers matters even more.

## The elephant in the room

- Khatabook and OkCredit already send reminders, mostly via SMS and WhatsApp. So I need to show why a voice call is **better**, not just different.
- A call might feel worse than a message. Some customers may find an automated call from the shop impersonal or insulting, which is the exact relationship damage the shopkeeper is trying to avoid.

## Current MVP validation

For the current MVP, we are focusing on one simple neighborhood kirana shop and using one shopkeeper's workflow as the initial source of truth. This is an early validation, not yet proof that the problem is the same for all kirana stores.

### Initial shop profile

- **Shop type:** Neighborhood kirana/general store
- **Location:** To be recorded
- **Current record-keeping:** Informal khata/notebook
- **Pending udhaar:** To be recorded by the shopkeeper
- **Current reminder method:** Personal follow-up by the shopkeeper
- **Preferred language:** Hindi/Hinglish, to be confirmed
- **Preferred calling time:** To be confirmed with the shopkeeper

### What has been validated so far

- The shopkeeper has a real need to follow up with customers about pending udhaar.
- The shopkeeper is willing to try a voice-based reminder sent on behalf of the shop.
- We have successfully triggered a call to a customer through the voice-agent workflow.
- The MVP currently focuses on a simple shopkeeper flow rather than supporting every possible shop type or payment process.

### What is still unknown

We have not yet collected enough evidence to generalize this solution. We still need to record:

- The shopkeeper's approximate total pending udhaar
- Exact shopkeeper/customer quotes
- Whether customers prefer calls over WhatsApp or SMS
- Whether automated calls feel respectful to customers
- Which languages and calling times work best
- What would make the shopkeeper stop using the product
- Whether the call results in a repayment promise or actual payment

These questions should be answered through additional shopkeeper and customer conversations after the initial working demo.

## Initial interview questions

We asked, or will ask, the shopkeeper:

1. "How much udhaar is pending right now, and how long do you think you'll have to wait for it?"
2. "How do you remind people today? What happens when you do?"
3. "What do you hate most about it?"
4. "Would you be okay with a call going out in your shop's name?"

**Their answers:** *(add verified answers and direct quotes here; do not invent quotes)*
