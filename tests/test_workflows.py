import csv
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models import Appointment, User

PASSWORD = 'LocalTest123!'
HASH = generate_password_hash(PASSWORD)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr('app.routes.now', lambda: datetime(2030, 1, 1, 8, 0))
    app = create_app({'TESTING': True, 'SECRET_KEY': 'test-only',
                      'SQLALCHEMY_DATABASE_URI': f'sqlite:///{(tmp_path / "test.db").as_posix()}'})
    with app.app_context():
        for name, role, doctor_id in [('Patient One', 'patient', None), ('Patient Two', 'patient', None),
                                       ('Doctor One', 'doctor', 1), ('Doctor Two', 'doctor', 2),
                                       ('Admin', 'admin', None)]:
            db.session.add(User(name=name, email=name.replace(' ', '').lower()+'@test.com',
                                role=role, doctor_id=doctor_id, password_hash=HASH))
        db.session.commit()
    return app


def signed(app, name='Patient One'):
    client = app.test_client()
    with app.app_context():
        uid = db.session.scalar(db.select(User.id).where(User.name == name))
    with client.session_transaction() as session:
        session['user_id'] = uid
        session['csrf'] = 'test-token'
    return client


def mutate(client, method='POST', path='/api/appointments', data=None):
    return client.open(path, method=method, json=data,
                       headers={'X-CSRF-Token': 'test-token'})


def booking(**changes):
    return dict(doctor_id=1, date='2030-01-02', time='09:00', **changes)


def test_full_shared_workflow(app,monkeypatch):
    patient, doctor, admin = signed(app), signed(app, 'Doctor One'), signed(app, 'Admin')
    result = mutate(patient, data=booking())
    assert result.status_code == 201
    record = result.json
    assert record['patient'] == 'Patient One'
    assert record['type'] == 'Online'
    for client in (patient, doctor, admin):
        assert client.get('/api/appointments').json['appointments'][0]['id'] == record['id']
    assert '09:00' not in patient.get('/api/availability?doctor_id=1&date=2030-01-02').json['slots']
    assert mutate(signed(app, 'Patient Two'), data=booking()).status_code == 409
    monkeypatch.setattr('app.routes.now',lambda: datetime(2030,1,2,10,0))
    assert mutate(doctor, 'PATCH', f'/api/appointments/{record["id"]}', {'status':'Completed'}).status_code == 200
    assert patient.get('/api/appointments').json['appointments'][0]['status'] == 'Completed'
    assert mutate(doctor, 'PATCH', f'/api/appointments/{record["id"]}', {'status':'No-show'}).status_code == 409


def test_cancellation_releases_slot(app):
    patient = signed(app)
    aid = mutate(patient, data=booking()).json['id']
    assert mutate(patient, 'PATCH', f'/api/appointments/{aid}', {'status':'Cancelled'}).status_code == 200
    assert '09:00' in patient.get('/api/availability?doctor_id=1&date=2030-01-02').json['slots']
    assert mutate(patient, data=booking()).status_code == 201


def test_block_unblock_and_conflict(app):
    patient, doctor = signed(app), signed(app, 'Doctor One')
    block = lambda method='POST': mutate(doctor, method, '/api/blocked-dates', {'date':'2030-01-02'})
    assert block().status_code == 200
    assert block().json['dates'] == ['2030-01-02']
    availability = patient.get('/api/availability?doctor_id=1&date=2030-01-02').json
    assert availability['blocked'] is True and availability['slots'] == []
    assert mutate(patient, data=booking()).status_code == 409
    assert block('DELETE').json['dates'] == []
    assert mutate(patient, data=booking()).status_code == 201
    assert block().status_code == 409


@pytest.mark.parametrize('changes', [
    {'date':'2029-12-31'}, {'date':'2030-01-01','time':'07:00'},
    {'date':'not-a-date'}, {'date':'2030-02-30'}, {'date':None},
    {'date':['2030-01-02']}, {'time':'09:10'}, {'time':None},
    {'doctor_id':999}, {'doctor_id':None}, {'doctor_id':True}, {'doctor_id':10**30},
])
def test_invalid_booking(app, changes):
    data = booking(); data.update(changes)
    assert mutate(signed(app), data=data).status_code == 400


def test_past_time_and_exact_time_rejected(app, monkeypatch):
    monkeypatch.setattr('app.routes.now', lambda: datetime(2030, 1, 1, 10, 0))
    admin = signed(app, 'Admin')
    for slot in ('09:00', '10:00'):
        data = booking(patient='Walk In'); data.update(date='2030-01-01', time=slot)
        assert mutate(admin, data=data).status_code == 400
    assert admin.get('/api/availability?doctor_id=1&date=2030-01-01').json['slots'] == ['10:30', '11:00', '13:00','13:30','14:00','14:30','15:00','15:30','16:00']


@pytest.mark.parametrize('name', ['   ', '', None, ['Name'], 'x'*121])
def test_walkin_name_validation(app, name):
    assert mutate(signed(app, 'Admin'), data=booking(patient=name)).status_code == 400


def test_walkin_shared_and_csv_safe(app):
    admin, doctor = signed(app, 'Admin'), signed(app, 'Doctor One')
    response = mutate(admin, data=booking(patient='=1+1'))
    assert response.status_code == 201
    assert response.json['type'] == 'Walk-in'
    assert doctor.get('/api/appointments').json['appointments'][0]['patient'] == '=1+1'
    exported = admin.get('/api/reports/appointments.csv')
    rows = list(csv.reader(io.StringIO(exported.data.decode('utf-8-sig'))))
    assert rows[1][0] == "'=1+1"
    assert 'attachment' in exported.headers['Content-Disposition']


def test_permissions_and_data_isolation(app):
    patient, other, doctor2 = signed(app), signed(app, 'Patient Two'), signed(app, 'Doctor Two')
    aid = mutate(patient, data=booking()).json['id']
    assert other.get('/api/appointments').json['appointments'] == []
    assert doctor2.get('/api/appointments').json['appointments'] == []
    for client in (other, doctor2):
        assert mutate(client, 'PATCH', f'/api/appointments/{aid}', {'status':'Cancelled'}).status_code == 403
    assert mutate(patient, 'PATCH', f'/api/appointments/{aid}', {'status':'Completed'}).status_code == 403
    assert patient.get('/admin/dashboard').status_code == 403
    assert patient.get('/api/reports/appointments.csv').status_code == 403
    assert mutate(patient, 'POST', '/api/blocked-dates', {'date':'2030-01-02'}).status_code == 403
    assert mutate(doctor2, data=booking()).status_code == 403
    assert app.test_client().get('/api/appointments').status_code == 401
    assert app.test_client().get('/doctor/dashboard').status_code == 302


def test_csrf_and_malformed_payload(app):
    client = signed(app)
    assert client.post('/api/appointments', json=booking()).status_code == 400
    assert client.post('/api/appointments', json=booking(),headers={'X-CSRF-Token':'é'}).status_code == 400
    assert mutate(client, data=[]).status_code == 400
    assert mutate(client, data=None).status_code == 400
    assert mutate(client, 'PATCH', '/api/appointments/999', {'status':'Cancelled'}).status_code == 404


def test_real_login_registration_and_logout(app):
    client = app.test_client()
    assert client.get('/login').status_code == 200
    with client.session_transaction() as session:
        token = session['csrf']
    data = dict(email='patientone@test.com', password='wrong', csrf_token=token)
    assert client.post('/login', data=data).status_code == 400
    data['password'] = PASSWORD
    assert client.post('/login', data=data).location.endswith('/patient/dashboard')
    assert client.get('/patient/dashboard').status_code == 200
    with client.session_transaction() as session:
        token = session['csrf']
    assert client.post('/logout', data={'csrf_token':token}).status_code == 302
    client.get('/register')
    with client.session_transaction() as session:
        token = session['csrf']
    data = dict(name='New Patient', email='new@test.com', password=PASSWORD, csrf_token=token, role='admin')
    assert client.post('/register', data=data).status_code == 302
    assert client.get('/admin/dashboard').status_code == 403


def test_dashboards_and_reference_doctors(app):
    for role, name in [('patient','Patient One'), ('doctor','Doctor One'), ('admin','Admin')]:
        client = signed(app, name)
        response = client.get(f'/{role}/dashboard')
        assert response.status_code == 200
        assert f'/static/{role}.js'.encode() in response.data
    assert len(signed(app).get('/api/doctors').json['doctors']) == 3


def test_persistence_across_app_restart(app):
    patient, doctor = signed(app), signed(app, 'Doctor One')
    aid = mutate(patient, data=booking()).json['id']
    mutate(doctor, 'POST', '/api/blocked-dates', {'date':'2030-01-03'})
    restarted = create_app(dict(TESTING=True, SECRET_KEY='test-only',
                               SQLALCHEMY_DATABASE_URI=app.config['SQLALCHEMY_DATABASE_URI']))
    assert signed(restarted).get('/api/appointments').json['appointments'][0]['id'] == aid
    assert signed(restarted, 'Doctor One').get('/api/blocked-dates').json['dates'] == ['2030-01-03']


def test_concurrent_bookings_only_one_wins(app):
    clients = [signed(app), signed(app, 'Patient Two')]
    barrier = Barrier(2)
    def attempt(client):
        barrier.wait()
        return mutate(client, data=booking()).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, clients))
    assert sorted(results) == [201, 409]


def test_concurrent_block_and_booking_are_consistent(app):
    patient, doctor = signed(app), signed(app, 'Doctor One')
    barrier = Barrier(2)
    def attempt(kind):
        barrier.wait()
        if kind == 'book':
            return mutate(patient, data=booking()).status_code
        return mutate(doctor, 'POST', '/api/blocked-dates', {'date':'2030-01-02'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ['book','block']))
    assert results in ([201,409], [409,200])


def test_no_show_and_terminal_status(app,monkeypatch):
    patient, doctor = signed(app), signed(app, 'Doctor One')
    aid = mutate(patient, data=booking()).json['id']
    monkeypatch.setattr('app.routes.now',lambda: datetime(2030,1,2,9,0))
    assert mutate(doctor, 'PATCH', f'/api/appointments/{aid}', {'status':'No-show'}).status_code == 200
    assert mutate(patient, 'PATCH', f'/api/appointments/{aid}', {'status':'Cancelled'}).status_code == 409


def test_demo_seed_is_explicit_and_idempotent(app, tmp_path):
    fresh = create_app({'TESTING': True, 'SECRET_KEY':'test-only',
                       'SQLALCHEMY_DATABASE_URI':f'sqlite:///{(tmp_path / "demo.db").as_posix()}'})
    runner = fresh.test_cli_runner()
    assert runner.invoke(args=['seed-demo','--password',PASSWORD]).exit_code == 0
    assert runner.invoke(args=['seed-demo','--password',PASSWORD]).exit_code == 0
    with fresh.app_context():
        assert len(list(db.session.scalars(db.select(User).where(User.email.like('%@mediqueue.test'))))) == 3


def test_seed_keeps_existing_doctor(app):
    result = app.test_cli_runner().invoke(args=['seed-demo','--password',PASSWORD])
    assert result.exit_code == 0
    assert 'Doctor already has an account' in result.output


def test_duplicate_registration_and_invalid_name(app):
    client = app.test_client(); client.get('/register')
    with client.session_transaction() as session:
        csrf = session['csrf']
    for name, email in [('Name','patientone@test.com'), ('   ','new@test.com')]:
        assert client.post('/register', data=dict(name=name,email=email,password=PASSWORD,csrf_token=csrf)).status_code == 400


def test_invalid_blocks_and_admin_status(app):
    doctor = signed(app,'Doctor One')
    for day in ('2029-12-31', None, 'bad'):
        assert mutate(doctor,'POST','/api/blocked-dates',{'date':day}).status_code == 400
    admin = signed(app,'Admin')
    aid = mutate(admin,data=booking(patient='Walk In')).json['id']
    assert mutate(admin,'PATCH',f'/api/appointments/{aid}',{'status':'Invented'}).status_code == 400
    assert mutate(admin,'PATCH',f'/api/appointments/{aid}',{'status':'Cancelled'}).status_code == 200


def test_past_cancellation_is_rejected(app, monkeypatch):
    client = signed(app)
    aid = mutate(client,data=booking()).json['id']
    monkeypatch.setattr('app.routes.now',lambda: datetime(2030,1,3,8,0))
    assert mutate(client,'PATCH',f'/api/appointments/{aid}',{'status':'Cancelled'}).status_code == 409


def test_one_hour_duration_and_neighboring_slots(app):
    patient = signed(app)
    result = mutate(patient,data=booking())
    assert result.status_code == 201
    assert result.json['duration_minutes'] == 60
    assert result.json['end_time'] == '10:00'
    assert patient.get('/api/availability?doctor_id=1&date=2030-01-02').json['slots'] == ['10:00','10:30','11:00','13:00','13:30','14:00','14:30','15:00','15:30','16:00']
    overlapping = booking(); overlapping['time'] = '09:30'
    assert mutate(patient,data=overlapping).status_code == 409
    adjacent = booking(); adjacent['time'] = '10:00'
    assert mutate(patient,data=adjacent).status_code == 201


def test_later_start_blocks_overlaps_on_both_sides(app):
    patient = signed(app)
    data = booking(); data['time'] = '09:30'
    result = mutate(patient,data=data)
    assert result.status_code == 201
    assert result.json['end_time'] == '10:30'
    slots = patient.get('/api/availability?doctor_id=1&date=2030-01-02').json['slots']
    assert slots == ['10:30','11:00','13:00','13:30','14:00','14:30','15:00','15:30','16:00']
    for start in ['09:00','10:00']:
        data['time'] = start
        assert mutate(patient,data=data).status_code == 409


def test_one_hour_conflicts_are_scoped_to_doctor_and_date(app):
    patient = signed(app)
    assert mutate(patient,data=booking()).status_code == 201
    data = booking(); data.update(doctor_id=2,time='09:30')
    assert mutate(patient,data=data).status_code == 201
    data.update(doctor_id=1,date='2030-01-03')
    assert mutate(patient,data=data).status_code == 201


def test_cancellation_releases_entire_hour(app):
    patient = signed(app)
    aid = mutate(patient,data=booking()).json['id']
    assert mutate(patient,'PATCH',f'/api/appointments/{aid}',{'status':'Cancelled'}).status_code == 200
    data = booking(); data['time'] = '09:30'
    assert mutate(patient,data=data).status_code == 201


def test_concurrent_overlapping_bookings_only_one_wins(app):
    clients = [signed(app),signed(app,'Patient Two')]
    barrier = Barrier(2)
    def attempt(pair):
        client, time = pair
        data = booking(); data['time'] = time
        barrier.wait()
        return mutate(client,data=data).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt,zip(clients,['09:00','09:30'])))
    assert sorted(results) == [201,409]


def test_doctor_calendar_receives_new_bookings_and_duration(app):
    doctor, patient = signed(app,'Doctor One'), signed(app)
    assert doctor.get('/api/appointments').json['appointments'] == []
    created = mutate(patient,data=booking()).json
    events = doctor.get('/api/appointments').json['appointments']
    assert len(events) == 1
    assert events[0]['id'] == created['id']
    assert (events[0]['patient'],events[0]['date'],events[0]['time'],events[0]['end_time']) == ('Patient One','2030-01-02','09:00','10:00')
    html = doctor.get('/doctor/dashboard').data
    for marker in (b'calendarGrid',b'doctor-calendar.js',b'weekView',b'dayView',b'appointmentDialog'):
        assert marker in html


def test_csv_contains_full_appointment_interval(app):
    admin = signed(app,'Admin')
    assert mutate(admin,data=booking(patient='Interval Test')).status_code == 201
    rows = list(csv.DictReader(io.StringIO(admin.get('/api/reports/appointments.csv').data.decode('utf-8-sig'))))
    assert rows[0]['Start Time'] == '09:00'
    assert rows[0]['End Time'] == '10:00'
    assert rows[0]['Duration (minutes)'] == '60'
