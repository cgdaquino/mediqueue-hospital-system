# MediQueue User Manual

## 1. Introduction
MediQueue is a hospital appointment and queue
management system with three user roles:
Patient, Doctor, and Administrator.

## 2. System Requirements
- Modern web browser
- Internet access for Codespaces development
- Running Flask application
- Authorized user account

## 3. Starting the Application
1. Open the GitHub Codespace.
2. Activate the Python virtual environment.
3. Run `python run.py`.
4. Open the forwarded port 5000.

On first setup, install the requirements and run `python -m flask --app run seed-demo`
to create demo accounts with a password you choose. See README.md for complete setup.

## 4. Patient Portal
Implemented workflow:

1. Register or log in.
2. Select a department.
3. Choose a doctor.
4. Select an available date and a time range. Its length is set by the doctor and shown beside the range.
5. Confirm the appointment.
6. View or cancel appointments.
7. For a cancelled appointment, optionally choose **Remove from my list**. It disappears
   from your list while the doctor/admin retain the cancelled record.

The initial roster has one active doctor per department: Dr. Maria Santos (General Medicine),
Dr. Ana Cruz (Cardiology), and Dr. Sofia Garcia (Pediatrics). Completion is recorded
by your doctor or an administrator after the appointment ends, not by the patient.
Action notifications appear at the bottom right and offer Undo for five seconds.
Undo may be refused if another change has already affected the record or slot.

A blocked or non-working date shows a red message directly beneath Appointment
Date. Choose a different date to clear it. On working dates, clinic and lunch hours
appear under the date; only complete consultations of the selected doctor's duration
that fit outside lunch are offered.

## 5. Doctor Portal
Implemented workflow:

1. Log in using a doctor account.
2. Open the appointment calendar.
3. View scheduled patients.
4. Update consultation statuses.
5. Manage unavailable dates.

Open **Weekly availability & lunch break** to set each day's working status, start
and finish time, and optional lunch break. Select **Save availability**. Defaults
are Monday–Friday 9 AM–5 PM with lunch noon–1 PM. Choose an appointment duration of
15, 30, 45, 60, 90, or 120 minutes before saving. The setting applies only to new
bookings; existing appointments retain their original length. A schedule change that conflicts with a future confirmed appointment
is rejected and identifies that appointment; resolve it before retrying.

Use the main Calendar/Queue tabs to choose your preferred display, then select a
date. The date selector is shared between both displays. Both show the same status
actions. Completed is enabled after the appointment ends; No-show after it starts.
Status changes and other saved actions offer a five-second Undo notification.
Use Week or Day to switch calendar views, the arrows to move through dates, or Today
to return to the current date. Select an appointment card to see its patient, full
time range, and status actions. New patient bookings appear in the doctor's visible
calendar within 10 seconds, or immediately after Refresh. Times use Philippine Time (PHT, UTC+8).
Block only dates with no confirmed appointments. Use Unblock to restore availability.
Blocked dates apply to both patients and administrators.
Lunch is shaded in the calendar. Non-working days are labeled Not working.
Cancelled appointments remain in the calendar as grey dashed cards, and remain in
the selected day's records. They have no status-action buttons and do not count as waiting.

The demo doctor account has a **Demo doctor POV** menu below the doctor's name.
Select Maria Santos, Ana Cruz, or Sofia Garcia to review that doctor's calendar,
queue, working hours, lunch, and duration. This switcher is unavailable to regular
doctor accounts. Use a separate browser session for each role during simultaneous review.

## 6. Administrator Portal
Implemented workflow:

1. Log in using an administrator account.
2. View hospital appointment statistics.
3. Search appointments by patient/doctor/reference and sort by name or date.
4. Filter by status. Mark completed after the session, no-show after its start, or cancel.
5. Register walk-in patients.
6. Export reports. Search filters do not restrict the CSV export.

Open **Doctor accounts** to create and manage doctor access. Choose a new doctor or
an existing profile without a login, enter their details and an initial password,
then create the account. Use **Edit account** to change details or set a new password;
leave the password blank to keep the current one. Account changes require the doctor
to sign in again. Passwords are never displayed after saving.

Deactivate an account to prevent sign-in and new bookings. Existing appointments
and history remain saved; review the upcoming count and resolve those bookings as
needed. Reactivate to restore access. Public registration creates patients only.
The initial demo doctor account belongs to Dr. Maria Santos. Regular doctor accounts
cannot use the demo POV switcher.
Walk-in registration rejects blank names, past times, blocked dates, and occupied slots.

## 7. Troubleshooting
- Check whether Flask is running.
- Check the Codespaces Ports tab.
- Verify Python dependencies are installed.
- Report unexpected errors to the development team.

## 8. Screenshots
See `evidence/blocked-date-test.jpg` for the integrated patient screen showing a
doctor-blocked date and the saved completion status. Test records are fictional.
The revised screens are in `evidence/mediqueue-doctor-revised.jpg`,
`evidence/mediqueue-admin-search.jpg`, `evidence/mediqueue-patient-revised.jpg`, and
`evidence/mediqueue-undo-notice.jpg`.
Doctor-account controls are shown in `evidence/mediqueue-doctor-accounts.jpg`.

## Document Status
Updated for the local integration on November 24, 2026. Appointments and blocked
dates persist in SQLite across page refreshes and application restarts. Each role
must sign in; patients see only their own bookings, and doctors see their assigned
queues. The doctor's calendar automatically checks for updates every 10 seconds;
admin records also refresh every 10 seconds. Reload patient screens to see changes
made by another user.
