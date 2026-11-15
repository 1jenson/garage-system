# Reminders — parked 14 Nov 2026

Jenson asked for Reminders to come out of the system for now:

> "remove the reminders for now from this system as if there is a mistake made and they dont recieve a reminder they would blame that on us"

## What changed in the mock (`mock/index.html`)
- One flag near the top of the script: `const REMINDERS_ON=false;`
- With the flag off: no Reminders entry in the sidebar, bottom tab bar or More page; the home tile is replaced by **Cancellation list** (waiting count, back link to Diary); the Settings "Reminder rules" tab and the MOT/service reminder templates are hidden; the customer "reminders" preference switch is hidden; the `#/reminders` route redirects to `#/waitlist`.
- Nothing is sent and no screen says "we'll remind you".

## What still shows, as plain facts
- MOT expiry (from DVLA) and next-service-due on the vehicle page and in Lookup.
- "Service done · set next service date" on an invoice still records the next service date; it just shows on the vehicle page.
- Ring-backs (customers who asked us to call) stay, they are our own notes, not reminders to customers.

## To bring Reminders back
Set `REMINDERS_ON=true` in `mock/index.html`. All reminder screens, templates, rules and the home tile return as they were. Bump `mock/sw.js` VERSION and run `./deploy.sh`.
