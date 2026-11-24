# Local integration test results

Date: November 24, 2026 (Asia/Singapore).
Base: main at cbae95b0a223c6ac32eb835c732956645711cfd9.
Local branch: local/integrate-portals. No GitHub push or merge was performed.

## Automated checks

`python -m pytest -q`: **146 passed in 39.03 seconds**.
`node --test tests/calendar.test.cjs tests/availability.test.cjs`: **10 passed**.
The original nine tests are retained; additional cases cover shared records,
authentication, patient registration, role and record ownership checks, CSRF,
malformed requests, invalid doctor IDs, dates and times, whitespace-only patient
names, cancellation/slot release, final statuses, blocked dates/unblocking,
CSV formula escaping, restart persistence, demo setup idempotence, simultaneous
bookings, and simultaneous booking/date blocking.

The one-hour scheduling checks cover both directions of partial overlap,
back-to-back consultations, cancellation releasing the full hour, independent
doctors/dates, simultaneous overlapping requests, full CSV intervals, and the
assigned doctor's feed receiving the same saved patient booking.

Calendar tests cover Monday week boundaries, month/year/leap-year navigation,
side-by-side layout of older overlapping records, 12-hour time ranges, rendered
week/day views, event details, blocked-day labels, navigation, and new arrivals
appearing on the automatic refresh callback.

Working-hours tests cover saved per-doctor weekdays/hours/lunch, enabling weekends,
no-lunch schedules, full-hour boundaries around breaks/closing, malformed schedules,
unchanged data after rejection, permissions, restart persistence, blocking precedence,
protection of future confirmed bookings, and simultaneous schedule changes/bookings.
Frontend tests also execute the actual scripts to check the inline date warning,
clearing it on an available date, lunch-hour text, working/lunch toggles, saving the
seven-day form, and calendar lunch/non-working-day indicators.

Duration/history regression cases cover all six allowed durations, invalid values,
snapshotting each appointment's length, mixed-duration overlap checks, lunch/closing
boundaries, stale booking forms, concurrent settings changes/bookings, preserving
existing booking lengths, and idempotent upgrades from an older SQLite schema.
Patient removal cases verify ownership, CSRF, cancelled-only behavior, idempotence,
restart persistence, slot release, and the cancelled record remaining visible in
doctor/admin views and CSV. Frontend cases exercise variable time labels, patient
removal controls, cancellation calendar cards/queue entries, and admin auto-refresh.

The final bug/logic check additionally covers the three-doctor roster, Manila
timezone, demo-only POV switching and private data scoping, stale role/doctor-tab
guards, completion/no-show time limits and permissions, server-enforced undo expiry,
actor/POV ownership, restoration conflicts, clinical status undo, hours/block undo,
and protection against older undo tokens reversing newer identical changes.
Frontend checks include Calendar/Queue tabs, disabled premature clinical actions,
admin search/sorting/filter persistence, and the five-second notification countdown.

JavaScript syntax checks passed for api.js, patient.js, doctor.js, doctor-calendar.js, working-hours.js, admin.js, and doctor-accounts.js.
`git diff --check` passed.

## Earlier browser checks before one-hour scheduling

- Anonymous portal access redirected to sign-in.
- Patient sign-in opened the patient dashboard.
- Booking Maria Santos for November 25 at 09:00 created MQ-0001.
- Reloading preserved that booking.
- Signing in as the assigned doctor displayed that patient's booking on the selected date.
- Marking it Completed saved the status and updated the queue counters.
- Blocking November 26 saved the unavailable date with an Unblock control.
- Admin sign-in displayed the same completed record and matching totals.
- A whitespace-only walk-in name was rejected with an on-screen message.
- A valid walk-in at 09:30 was saved and appeared in admin totals/table.
- Earlier times on November 24 were unavailable and the submit button was disabled.
- CSV download contained the saved online and walk-in records.
- Returning to the patient account displayed Completed: 1 and the saved status.
- Selecting Maria Santos on November 26 displayed unavailable, offered no times,
  and kept booking disabled.
- No JavaScript errors were captured in the integrated browser test.

## One-hour calendar live-app check

Two independently authenticated HTTP clients signed in as the demo patient and
demo doctor against the running Flask application. A patient booking on November
27, 2026, 09:00–10:00 (MQ-0004) returned 201 and immediately appeared in the doctor's
schedule data with its 60-minute duration and matching end time.

The browser controller timed out while trying to open the new calendar, including
after a reset. Visual browser inspection and a new calendar screenshot could not be
completed in this session. The rendering/navigation/refresh checks above used a
simulated document with the actual frontend scripts. They do not replace a visual
layout check in a real browser. The prior screenshot is retained as historical evidence.
The same browser-control error also prevented visual inspection of the subsequent
inline-warning and weekly-hours updates.

## Variable-duration and cancellation live-app check

Independent authenticated doctor, patient, and admin HTTP clients exercised the
running app. The doctor saved a 30-minute duration; a new patient booking stored
30 minutes; the patient cancelled it and removed it from their list; it disappeared
only from that patient's response and stayed Cancelled in both staff responses.
The doctor's original duration/weekly settings were restored after this check.
Existing appointments were not changed. Browser controls again timed out, so the
new controls have automated rendering/behavior coverage but no new visual screenshot.

## Final batch revision browser and live-app checks

Browser access recovered. In the actual local app, the demo switcher opened Maria
Santos/General Medicine, Ana Cruz/Cardiology, and Sofia Garcia/Pediatrics. The Queue
tab showed the selected day's saved history; Calendar restored the week view. A
temporary December 2 unavailable date displayed the bottom-right Undo (5s) notice;
clicking Undo successfully removed that temporary block. The prior November 26
block was retained. Admin search for Ana with doctor-name sorting displayed one
matching appointment. The patient screen showed only Maria Santos under General
Medicine, the clinician-controlled completion explanation, PHT labels, and the red
blocked-date warning directly beneath the date field. No JavaScript errors were
captured in these checks. Four new screenshots are stored under docs/evidence.

The live HTTP check independently confirmed all three POVs, one doctor per department,
PHT labels, Calendar/Queue controls, admin search controls, premature completion
rejection, patient clinical-outcome rejection, and cancellation/removal undo. Final
stale-context and record-version guards were checked by automated regression tests.
Older demo records, including results entered before the new completion time rule,
are retained; no appointment history was deleted to make the test data look clean.

## Portal design refresh checks

The home page was visually checked at the default desktop viewport and at
390×844. Portal cards remain readable and the mobile layout stacks without
horizontal overflow. Keyboard focus selected the patient, doctor, and admin
photo scenes in sequence, then restored the exterior scene when focus left the
cards. The patient portal link opened the authenticated patient dashboard.
The registration screen explicitly stated patient-only registration and showed
the low-opacity patient-care photo behind an opaque form. The patient dashboard's
panels remained readable over its subtle background; no JavaScript errors were
captured. Button transitions are restrained and the stylesheet includes a
prefers-reduced-motion override. No scheduling or permission rules changed.

Four local stock images and their source/license credits are included. New evidence:
mediqueue-home-design.jpg, mediqueue-home-mobile.jpg,
mediqueue-registration-design.jpg, mediqueue-patient-background.jpg.

## Doctor-account management checks

Automated cases cover admin-only creation and editing, linking existing profiles,
patient-only public registration, rejected role/demo privilege inputs, password
hashing, default weekly schedules, validation, duplicate email/profile conflicts,
session revocation, deactivation with retained appointments, reactivation, and
restart persistence. Department changes cannot displace future confirmed bookings.
The legacy retirement migration no longer overrides later administrator activation.

In the browser, the admin panel loaded the roster, selecting an existing profile
filled its doctor details, and editing an account left its password blank and optional.
No account was created or changed in the live demo database during this visual check.
No JavaScript errors were captured. The homepage circles were enlarged proportionally
to their white arches; desktop cards measured 253px with 219px circles and an even rim.
Desktop and 390px mobile screenshots were refreshed. Account-panel evidence is
mediqueue-doctor-accounts.jpg.

## Admin-created doctor booking journey

A new regression test uses an admin-created account, real password sign-in, saved
30-minute consultations, changed working hours and lunch, patient roster/availability,
patient booking, the assigned doctor's calendar feed, admin visibility, slot release
protection, and exclusion from another doctor's feed.

The browser workflow used a separate temporary SQLite database on port 5056.
An authenticated admin created Dr. Workflow Test through the account API. The doctor
signed in through the form and saved 30-minute consultations with Wednesday hours
10:00–16:00 and lunch 12:00–13:00. A patient selected this doctor under Cardiology,
saw only the saved hours outside lunch, and booked January 2, 2030, 10:00–10:30.
Signing back in as the new doctor displayed that patient on the weekly calendar;
opening the event showed the same patient, reference, time range and status.
The simulated hospital clock was January 1, 2030 for this isolated workflow.
The main demo database and roster were not changed. Evidence:
mediqueue-new-doctor-calendar.jpg.

## About Us visual check

The homepage About us link opened the team page. Each of the five user-supplied
photos loaded with its matching supplied full name. Desktop and 390px layouts
were inspected; the mobile grid had no horizontal overflow. Images have descriptive
alternative text, and the page links back to the portals. No JavaScript errors were
captured. Evidence: mediqueue-about-us.jpg and mediqueue-about-mobile.jpg.

## Final three-portal bug and logic review

Reviewed role/record ownership, patient-only registration, account activation and
session revocation, working hours/lunch/duration, overlap prevention and schedule
locking, calendar/queue rendering, clinical time limits, cancellation/removal, undo
ownership/expiry/conflicts, and admin search/sort/export. All 138 Python tests and
10 frontend tests passed. Every local JavaScript file passed its syntax check;
git diff --check passed.

Two deactivation edge cases were fixed and covered by new regression tests:
booking now rechecks the doctor's active status after acquiring the scheduling
write lock, and undo cannot reconfirm an appointment for an inactive doctor.

In a fresh isolated browser workflow, an admin registered a walk-in for the new
doctor and searched/sorted the record. The same booking appeared on that doctor's
calendar and selected-day queue. Premature completion/no-show buttons were disabled.
The doctor cancelled it, and a patient could book its released slot. The patient
then cancelled and removed their own booking; their list became empty while the
admin retained both cancelled records, distinguished as Walk-in and Online. No
JavaScript errors were captured. Evidence: mediqueue-final-admin-history.jpg.
These checks used a separate temporary database and did not alter the demo roster
or appointment history on port 5055. Automated tests also cover successful clinical
outcomes after their permitted times, CSV output, persistence, and concurrent requests.

The About Us page now credits the supplied contributions: Doctor Portal Developer
(Abug), Full Stack Integration Developer (Aquino), Admin Portal Developer (Asi),
Patient Portal Developer (Quiatchon), and Database Developer (Vijar). Desktop and
390px mobile layouts were rechecked; all five photos loaded without horizontal
overflow. Updated screenshots replace the earlier team-page evidence.

No blocking issue remains in the tested local workflows. This check does not cover
production hosting or every possible browser/device combination.

## Evidence and limits

Deliverable preparation added eight pure patient-registration validation tests.
Their actual test-first red run produced eight failures against an explicit
NotImplementedError boundary; implementation then passed all eight tests in 1.16s.
The helper is integrated in POST /register and the final complete suite passed 146
tests. This demonstrates one newly selected TDD function, not a claim that all
earlier development followed TDD. The supplied deliverable package retains raw
red/green/full-suite logs and a screenshot of their log viewer.

Thirteen additional live HTTP checks matched expected statuses using independent
clients and an isolated fictional database. They are not Postman evidence. The
33-request Postman collection is prepared but requires actual Postman execution
and screenshots before final submission.

See evidence/blocked-date-test.jpg. The automated JUnit results accompany the source
package. All records used here are fictional. This is regression and workflow testing,
not a claim that every possible input, device, or production environment was tested.
Database restart persistence and simultaneous requests were tested automatically;
the earlier browser exercise used a desktop viewport and local SQLite. The doctor
calendar and admin records now poll while visible every 10 seconds; patient tabs require reload.
Offline styling, email delivery, push notifications, password recovery,
are outside this integration.

The package excludes the local database, session secret, and virtual environment.
Run the setup instructions in README.md to create a fresh instance and demo accounts.

## Actual Postman verification completed

November 24, 2026 at 18:31:56 PHT: the actual Postman Web collection runner
used official Desktop Agent 0.5.4 against the isolated fictional app on port 5056.
All 33 requests completed; 36 assertions passed, zero failed/skipped and zero errors.
Duration: 9s 59ms; average response time: 133 ms.
Eleven screenshots in docs/evidence/Postman cover the summary, HTTP methods,
409 overlap and 403 role rejection, and retained cancelled history.
Postman-observed-run.json records observed UI data; it is not a native Postman
result export. The supplied CSV reconciles all 33 requests and 36 assertions.
This supersedes earlier pending-Postman notes in this historical test record.
No main demo data was changed, and no commit, push or merge was performed.
