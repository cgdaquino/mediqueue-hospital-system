# MediQueue Test Plan

## Project
MediQueue Hospital Appointment and Queue Management System

## Testing Objectives
Verify that appointment booking, authentication,
scheduling, queue management, and administrative
functions behave according to the requirements.

## Test Cases

| ID | Feature | Test Scenario | Expected Result |
|---|---|---|---|
| TC-01 | Homepage | Open homepage | Page loads successfully |
| TC-02 | API | GET /api/health | Returns HTTP 200 |
| TC-03 | Login | Valid credentials | Login succeeds |
| TC-04 | Login | Invalid password | Access denied |
| TC-05 | Booking | Available slot | Appointment confirmed |
| TC-06 | Booking | Duplicate slot | Second booking rejected |
| TC-07 | Booking | Past date | Booking rejected |
| TC-08 | Cancellation | Cancel future appointment | Status becomes Cancelled |
| TC-09 | Queue | View doctor's queue | Correct order displayed |
| TC-10 | Walk-in | Register valid walk-in | Appointment created |
| TC-11 | Permissions | Patient accesses admin API | HTTP 403 |
| TC-12 | Reports | Admin views statistics | Correct totals displayed |

## Testing Methods
- Unit Testing: Pytest
- Integration Testing: Flask test client
- Functional Testing: Browser
- Black Box Testing: Input/output scenarios
- API Testing: Postman

## Evidence
Store screenshots in docs/evidence/.

## TDD Evidence
For selected backend functions, capture:

1. Failing test before implementation (Red)
2. Passing test after implementation (Green)
3. Passing tests after refactoring (Refactor)

## Results
Record actual outcomes only after executing tests.
Do not mark untested scenarios as passed.