# RoleReady 🎯
### Don't watch training. Live it.

RoleReady replaces passive onboarding with AI-powered simulations.
Instead of watching videos and clicking "complete", employees practice
the actual job — with a realistic AI character — before facing a real
situation.

---

## The Problem

Companies mark employees "trained" after they watch a module. But
watching a video about handling an angry customer is not the same as
handling one. The first real call, the first incident, the first tough
conversation — all happen with zero prior practice.

RoleReady fixes that.

---

## Example: Arjun Joins as a Customer Success Rep — Day 2

His manager sends a RoleReady link. No Confluence doc. No video.

**Scenario assigned:**
You're calling Neha Joshi, Head of Ops at RetailCo.
2-year customer. Zero logins for 45 days. Renewal in 3 weeks.
She picks up. Sounds distracted.
Goal: Find out why engagement dropped. Don't offer a discount yet.

text

**Arjun types:**
> "Hi Neha! We noticed you haven't logged in recently and wanted
> to check in!"

**Neha (AI):**
> "Oh, hi. We've just been busy. The platform's fine I guess."

**[Live coaching — only Arjun sees this]**
> ⚠️ *Leading with inactivity data feels like surveillance, not care.
> Ask about their business first.*

**Arjun tries again:**
> "Sounds like a hectic quarter — what's been keeping the team busy?"

**Neha (AI):**
> "Honestly, we restructured. Half the team that used Zephyr daily
> moved departments. We haven't figured out the new workflow yet."

**[Live coaching]**
> ✅ *Good discovery. This isn't churn from dissatisfaction —
> it's an onboarding gap. Offer a re-onboarding session.*

---

**After the session, Arjun sees his score:**
Discovery Questioning 72% ↑
Tone & Empathy 68% ↑
Policy Adherence 91% ✅
Premature Solutions 55% ⚠️ needs work

text

**His manager sees:**
Arjun — Flag: jumps to solutions before understanding the problem
Priya — Flag: tone breaks under pressure
Rahul — On track ✅

text

Manager books a 15-min session with Arjun. Not a gut feeling —
the data showed exactly what to work on.

---

## Adding a New Role — No Code Needed

```json
{
  "role": "Sales Rep",
  "persona": {
    "name": "Vikram", "title": "CTO at a startup",
    "mood": "skeptical but fair",
    "trigger_positive": "specific technical questions",
    "trigger_negative": "generic pitch openers"
  },
  "scoring_rubric": {
    "discovery": "Did rep ask about current stack before pitching?",
    "next_step": "Did rep secure a concrete follow-up?"
  },
  "difficulty": "medium"
}
```

Drop in a JSON. The simulation runs. No engineering required.

---