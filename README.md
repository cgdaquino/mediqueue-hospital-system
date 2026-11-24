# MediQueue

Hospital appointment and queue management built with Flask and SQLite.

CS0053 final project, Appointment Scheduling System option. Team responsibilities:
Sidfrey F. Abug (Doctor Portal), Casey Gabrielle D. Aquino (Full Stack Flask
Integration), Christine Nicole E. Asi (Admin Portal), Lord Grey D. Quiatchon
(Patient Portal), and JM D. Vijar (Database). The Git history additionally records
testing and documentation contributions.

## Run locally

Use Python 3.11 or newer. From the repository folder:

```sh
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux/Codespaces: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m flask --app run seed-demo
python run.py
```

The setup command prompts for a demo password of at least eight characters.
It creates `patient@mediqueue.test`, `doctor@mediqueue.test` (Maria Santos),
and `admin@mediqueue.test`. Existing users/passwords are never overwritten.
If Maria Santos already has a doctor account, that account is retained.
Patients can also register at `/register`; registration cannot create staff accounts.
Patient registration validates names and email format and requires a password of
8–128 characters with at least one non-space character. It normalizes the name
and email while preserving the password exactly.
Admins can open **Doctor accounts** in their dashboard to create a doctor/login,
link a login to an existing doctor, edit details, reset passwords, or deactivate and
reactivate access. Deactivation preserves appointment history and shows upcoming
confirmed bookings for review. Account changes revoke that doctor's existing sessions.

Open `http://127.0.0.1:5000`. Sign in through `/login`, or use the portal links.
Routes are `/patient/dashboard`, `/doctor/dashboard`, and `/admin/dashboard`.
Each account can access only its own role. Doctors see their assigned queue;
patients see only their own appointments. Admins see all appointments and walk-ins.

SQLite tables and three active doctors (one each for General Medicine, Cardiology,
and Pediatrics) are created at startup. The older duplicate General Medicine
doctor is retired from new bookings while its historical records remain saved. Appointments
and blocked dates are stored in `instance/mediqueue.db`, not in the browser.
The local session secret is kept in `instance/session-secret`; both are ignored by Git.
An optional `SECRET_KEY` environment variable overrides that secret.
`DATABASE_URL` may point to another SQLite database. The schedule locking and
partial unique index currently target SQLite, not other database engines.
Back up the instance folder before changing an existing installation.
The startup upgrade adds missing duration and patient-visibility columns to older
SQLite databases without deleting records. Legacy bookings keep their original
60-minute duration. This small upgrade is idempotent; arbitrary future schema
changes will still need their own migrations.

## Scheduling rules

- Hospital time uses `Asia/Manila` (Philippine Time, PHT, UTC+8), independently of the browser's timezone.
- Each doctor has a saved weekly schedule. New doctors default to Monday–Friday,
  09:00–17:00, with lunch 12:00–13:00 and weekends closed. Doctors can edit these
  settings under **Weekly availability & lunch break**, including working days,
  start/finish, appointment duration, and an optional lunch break for each day. Times use 15-minute increments;
  overnight shifts are not supported. This adds a new table without changing existing bookings.
- Available starts are generated inside the saved schedule, at 15-minute intervals
  for 15/45-minute consultations and 30-minute intervals for the other durations.
  The full consultation must fit before closing and must not overlap lunch.
  Patient and admin booking requests enforce the same rules on the server.
- Doctors choose 15, 30, 45, 60, 90, or 120 minutes for new bookings. Patients and
  admins see explicit start/end ranges and the duration. Existing bookings store
  their own duration and never resize when the doctor's setting changes.
  Start options remain flexible, but overlapping intervals for the same doctor are
  rejected, including simultaneous requests. For example, 09:00–10:00 prevents
  09:30–10:30; 10:00–11:00 can follow it immediately.
- Bookings must be in the future with a real doctor and a nonblank patient name.
- A doctor cannot have overlapping occupied appointments. Cancelling releases the occupied interval.
- Blocking a date prevents both online and walk-in bookings. A date with confirmed
  appointments must be resolved before it can be blocked. Doctors can unblock dates.
- Saving weekly hours also rejects changes that would displace future confirmed
  appointments. An administrator can resolve/cancel the conflicting appointments first.
  Date blocks override the recurring weekly schedule.
- Blocked or non-working dates show a red warning directly below the patient's
  date selection. Available dates show clinic and lunch hours there instead.
- Bookings are automatically Confirmed when created. Only the assigned doctor or
  an admin can mark Completed after the appointment ends, or No-show after it starts.
  Both can cancel confirmed appointments. Patients cannot mark clinical outcomes.
  Terminal statuses cannot normally be changed; a safe five-second undo is the exception.
- Patients can cancel only their own future, confirmed appointments.
- Cancelled records remain visible to doctors and admins, including grey/dashed
  calendar cards. Doctors' active counters exclude them. Patients can then choose
  **Remove from my list**: this hides only their own cancelled entry, leaving the
  hospital record, staff views, and CSV export intact. Active appointments cannot
  be removed, and patients cannot remove anyone else's entries.
- All writes require a session CSRF token. Conflicts return 409, invalid input 400,
  unauthenticated API access 401, and forbidden access 403.
- The doctor's calendar provides Monday–Sunday week and day views, previous/next,
  Today, a date picker, blocked/non-working days, lunch shading, status colors, and appointment details.
  Selecting a day updates its queue; selecting an event opens its details/actions.
  While visible, the calendar checks for new bookings every 10 seconds, refreshes
  when the tab is refocused, and also provides a Refresh button. Admin records also
  refresh every 10 seconds while visible, so patient cancellations appear without
  reloading. Patient screens load current records when opened/reloaded.
- Doctors can select Calendar or Queue using the main display tabs. Both expose
  the same eligible status actions; calendar cards open an appointment detail dialog.
- The seeded `doctor@mediqueue.test` account has a demo-only doctor POV selector.
  It switches between the three active doctors without changing anyone's account
  assignment. Ordinary doctor accounts cannot switch. A stale tab is reloaded or
  refused before it can show or change the wrong doctor's records.
- Small bottom-right action notifications offer Undo for five seconds after booking,
  cancellation/removal, clinical status changes, date blocking/unblocking, and saving
  hours/duration. Expiry is checked by the server. Undo refuses conflicting changes,
  rebooked slots, another user's action, or an action from a different demo POV.
- Admin Appointment Management supports patient/doctor/reference search, patient or
  doctor name sorting, earliest/latest date sorting, and status filtering. Filters
  persist while the data refreshes; counters and CSV export still use all records.
- Different role accounts need separate browser profiles or private sessions when
  tested simultaneously. Tabs in one browser share the login. Stale role tabs are
  sent back to sign-in instead of rendering another role's data.
- Existing records keep their start times. If older records overlap, the calendar
  shows them side by side. New bookings cannot add overlapping occupied intervals.

## Tests

```sh
python -m pytest -q
node --test tests/calendar.test.cjs tests/availability.test.cjs
```

Tests use temporary databases. They cover permissions, session login, registration,
CSRF, validation, shared booking/status changes, cancellation, blocking, CSV export,
restart persistence, simultaneous bookings, and simultaneous booking/date blocking.
Further cases cover all duration options, mixed old/new appointment lengths,
stale client durations, schedule-change races, cancellation visibility, patient-only
removal, retained staff/CSV history, and upgrading legacy SQLite databases.
The original homepage and template checks are retained.
The calendar tests require Node.js 18 or newer and check date boundaries, event
layout, explicit time ranges, navigation, details, and newly arriving appointments.

The development UI still loads Tailwind from its CDN, so styling needs internet.
The home page has its own local stylesheet, rounded-top portal cards, decorative
SVG role icons, and local stock-photo backgrounds. Hospital exterior is the default;
pointer hover or keyboard focus switches to patient, doctor, or administration imagery.
Dashboard and sign-in/register pages use quieter role-specific photo backgrounds.
Buttons lift/scale slightly on hover and press gently on click; reduced-motion
preferences disable these transitions. Photo sources and license are in
`docs/PHOTO_CREDITS.md`. Registration text explicitly states patient-only access.
The homepage **About us** link introduces the five creators with their supplied
portraits and names. The portraits are included locally in `app/static/images/team`.
This is a local class-project application; production deployment, password recovery,
email delivery, and push notifications are not included.
