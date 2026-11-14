# Data model · cancellation list

The Cancellation List (`#/waitlist`, the old `#/motlist` still works) is one store shared by the Diary and the list page. Every customer waiting for an earlier MOT or job slot is one row, whether they were flagged from a diary booking or added by hand. The mock keeps these in memory; this is the shape the real tables will take.

## waitlist

| column | type | notes |
|---|---|---|
| id | uuid | |
| booking_id | uuid, nullable | the diary booking this row was flagged from; null when added by hand |
| reg | text | registration, normalised upper case |
| customer | text | name |
| phone | text | |
| type | `mot` \| `job` | prefilled from the booking kind, editable |
| booked_date | date, nullable | the slot they currently hold |
| booked_time | time, nullable | MOTs only; jobs have no fixed time |
| earliest_date | date | earliest day they could come in |
| time_pref | `any` \| `am` \| `pm` | any day / mornings / afternoons |
| notes | text | |
| status | `waiting` \| `moved` \| `rebooked` \| `removed` \| `kept` \| `done` | moved = earlier slot, rebooked = later slot |
| new_date | date, nullable | slot they were moved or rebooked into |
| new_time | time, nullable | |
| original_date | date, nullable | the slot they held when first moved; kept so a move can be undone |
| original_time | time, nullable | |
| mot_expiry | date, nullable | refreshed from the DVSA MOT history lookup, not typed in |
| created_by | staff id | who flagged them |
| created_at | timestamptz | |
| updated_by | staff id | |
| updated_at | timestamptz | |

## waitlist_history

One line per change, shown on the card under History.

| column | type | notes |
|---|---|---|
| id | uuid | |
| waitlist_id | uuid | → waitlist.id |
| at | timestamptz | |
| by | staff id | |
| text | text | e.g. `Moved forward from Tue 25 Nov 13:00 to Thu 20 Nov 09:00`, `Put back to original slot Tue 25 Nov 13:00 from Thu 20 Nov 09:00`, `Removed from diary` |

## How the diary uses it

- **Flag**: "Waiting for earlier slot" on a booking inserts a `waiting` row with `booking_id`, type from the booking, earliest date, time preference and notes, plus a history line. The booking shows a Waiting badge and the button becomes "On the waiting list".
- **Slot freed**: taking a booking out of the diary marks its own row `removed` (if it had one) and offers the freed slot to `waiting` rows of the same type whose earliest date is on or before the slot and whose current booking is later, best time-preference fit first, then earliest date. "Move here" moves the diary booking, sets `original_*` (first time only), `new_*`, status `moved`, and writes the history line.
- **Moved by hand**: moving a flagged booking in the Diary itself marks the row `moved` (earlier) or `rebooked` (later) with the same fields.
- **Put back to original slot**: on a moved or rebooked card. Restores the diary booking to `original_*`, clears `new_*`, returns the row to `waiting` and logs it. Refused if an MOT slot has since been taken.
- **Done / still booked**: a `done` row whose `booked_date` is today or later is shown in the red alert box until the booking is removed from the diary.

MOT expiry is never typed in by staff on the real system: the diary refresh pulls it from the DVSA lookup (8am, 12pm, 5pm Mon–Fri) and the card links to the public MOT history page.
