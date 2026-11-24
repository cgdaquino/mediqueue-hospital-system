import pytest

from app import create_app,db
from app.models import Doctor,User,WeeklyAvailability
from test_workflows import app,signed,mutate,booking,PASSWORD


def doctor_data(**changes):
    data=dict(name='Dr. Account Test',email='newdoctor@test.com',department='Cardiology',password='DoctorPass123!',active=True)
    data.update(changes); return data


def login(app,email,password):
    client=app.test_client(); client.get('/login')
    with client.session_transaction() as state: token=state['csrf']
    response=client.post('/login',data=dict(email=email,password=password,csrf_token=token))
    return client,response


def test_admin_creates_doctor_with_schedule_and_real_login(app):
    admin=signed(app,'Admin')
    response=mutate(admin,'POST','/api/admin/doctors',doctor_data(role='admin'))
    assert response.status_code == 400
    response=mutate(admin,'POST','/api/admin/doctors',doctor_data())
    assert response.status_code == 201
    did=response.json['doctor_id']
    assert response.json['email'] == 'newdoctor@test.com'
    assert 'password' not in response.json and 'password_hash' not in response.json
    with app.app_context():
        user=db.session.scalar(db.select(User).where(User.doctor_id == did))
        assert user.role == 'doctor' and user.demo_doctor is False
        assert user.password_hash != 'DoctorPass123!'
        assert len(list(db.session.scalars(db.select(WeeklyAvailability).where(WeeklyAvailability.doctor_id == did)))) == 7
    client,response=login(app,'newdoctor@test.com','DoctorPass123!')
    assert response.status_code == 302 and response.location.endswith('/doctor/dashboard')
    assert client.get('/doctor/dashboard').status_code == 200
    assert client.get('/admin/dashboard').status_code == 403
    with client.session_transaction() as state: token=state['csrf']
    assert client.post('/api/demo/doctor-pov',json={'doctor_id':1},headers={'X-CSRF-Token':token}).status_code == 403


def test_link_existing_profile_without_duplicate_doctor(app):
    admin=signed(app,'Admin')
    response=mutate(admin,'POST','/api/admin/doctors',doctor_data(doctor_id=3,name='Dr. Sofia Garcia',department='Pediatrics'))
    assert response.status_code == 201 and response.json['doctor_id'] == 3
    assert len(signed(app).get('/api/doctors').json['doctors']) == 3
    assert mutate(admin,'POST','/api/admin/doctors',doctor_data(doctor_id=3,email='another@test.com')).status_code == 409


def test_admin_created_doctor_full_patient_booking_journey(app):
    admin=signed(app,'Admin')
    created=mutate(admin,'POST','/api/admin/doctors',doctor_data())
    assert created.status_code == 201
    did=created.json['doctor_id']
    doctor,response=login(app,'newdoctor@test.com','DoctorPass123!')
    assert response.status_code == 302
    with doctor.session_transaction() as state: csrf=state['csrf']
    settings=doctor.get('/api/working-hours').json
    for day in settings['days']:
        day.update(start='10:00',end='16:00',lunch_start='12:00',lunch_end='13:00')
    saved=doctor.put('/api/working-hours',json={'days':settings['days'],'duration_minutes':30},headers={'X-CSRF-Token':csrf})
    assert saved.status_code == 200 and saved.json['doctor_id'] == did
    patient=signed(app)
    listed=next(row for row in patient.get('/api/doctors').json['doctors'] if row['id'] == did)
    assert listed['name'] == 'Dr. Account Test' and listed['department'] == 'Cardiology'
    available=patient.get(f'/api/availability?doctor_id={did}&date=2030-01-02').json
    assert available['duration_minutes'] == 30
    assert '10:00' in available['slots'] and '09:00' not in available['slots'] and '12:00' not in available['slots']
    result=mutate(patient,data={'doctor_id':did,'date':'2030-01-02','time':'10:00','duration_minutes':30})
    assert result.status_code == 201
    appointment=result.json
    events=doctor.get('/api/appointments').json['appointments']
    assert len(events) == 1 and events[0]['id'] == appointment['id']
    assert events[0]['patient'] == 'Patient One' and events[0]['end_time'] == '10:30'
    assert events[0]['duration_minutes'] == 30
    assert signed(app,'Doctor One').get('/api/appointments').json['appointments'] == []
    assert any(row['id'] == appointment['id'] for row in admin.get('/api/appointments').json['appointments'])
    assert '10:00' not in patient.get(f'/api/availability?doctor_id={did}&date=2030-01-02').json['slots']


@pytest.mark.parametrize('role',['Patient One','Doctor One'])
def test_non_admin_cannot_manage_accounts(app,role):
    client=signed(app,role)
    assert client.get('/api/admin/doctors').status_code == 403
    assert mutate(client,'POST','/api/admin/doctors',doctor_data()).status_code == 403
    assert mutate(client,'PATCH','/api/admin/doctors/1',{'active':False}).status_code == 403


def test_anonymous_and_csrf_rejected(app):
    assert app.test_client().get('/api/admin/doctors').status_code == 401
    assert signed(app,'Admin').post('/api/admin/doctors',json=doctor_data()).status_code == 400


@pytest.mark.parametrize('changes',[
    {'name':'   '},{'email':'not-an-email'},{'email':['bad']},{'department':'Unknown'},
    {'password':'short'},{'password':'x'*129},{'active':'true'},{'doctor_id':True},
    {'role':'admin'},{'demo_doctor':True},{'password_hash':'pretend'},
])
def test_invalid_account_data_is_rejected(app,changes):
    assert mutate(signed(app,'Admin'),'POST','/api/admin/doctors',doctor_data(**changes)).status_code == 400
    assert len(signed(app).get('/api/doctors').json['doctors']) == 3


def test_duplicate_email_and_unknown_profile_rejected(app):
    admin=signed(app,'Admin')
    assert mutate(admin,'POST','/api/admin/doctors',doctor_data(email='patientone@test.com')).status_code == 409
    assert mutate(admin,'POST','/api/admin/doctors',doctor_data(doctor_id=999)).status_code == 404
    assert mutate(admin,'POST','/api/admin/doctors',doctor_data(doctor_id=1)).status_code == 409


def test_update_details_and_password_revokes_old_sessions(app):
    admin,old=signed(app,'Admin'),signed(app,'Doctor One')
    assert old.get('/api/appointments').status_code == 200
    response=mutate(admin,'PATCH','/api/admin/doctors/1',{'name':'Dr. Updated','email':'updated@test.com','password':'NewDoctor123!'})
    assert response.status_code == 200
    assert old.get('/api/appointments').status_code == 401
    assert login(app,'doctorone@test.com',PASSWORD)[1].status_code == 400
    assert login(app,'updated@test.com',PASSWORD)[1].status_code == 400
    client,result=login(app,'updated@test.com','NewDoctor123!')
    assert result.status_code == 302
    assert client.get('/api/appointments').status_code == 200
    assert b'Dr. Updated' in client.get('/doctor/dashboard').data


def test_deactivation_retains_bookings_and_revokes_access_and_reactivation_persists(app):
    patient,doctor,admin=signed(app),signed(app,'Doctor One'),signed(app,'Admin')
    aid=mutate(patient,data=booking()).json['id']
    response=mutate(admin,'PATCH','/api/admin/doctors/1',{'active':False})
    assert response.status_code == 200 and response.json['future_confirmed'] == 1
    assert doctor.get('/api/appointments').status_code == 401
    assert login(app,'doctorone@test.com',PASSWORD)[1].status_code == 400
    assert all(row['id'] != 1 for row in patient.get('/api/doctors').json['doctors'])
    assert admin.get('/api/appointments').json['appointments'][0]['id'] == aid
    assert patient.get('/api/appointments').json['appointments'][0]['status'] == 'Confirmed'
    assert mutate(patient,data=booking()).status_code == 400
    assert mutate(admin,'PATCH','/api/admin/doctors/1',{'active':True}).status_code == 200
    assert doctor.get('/api/appointments').status_code == 401
    assert login(app,'doctorone@test.com',PASSWORD)[1].status_code == 302
    restarted=create_app({'TESTING':True,'SECRET_KEY':'test-only','SQLALCHEMY_DATABASE_URI':app.config['SQLALCHEMY_DATABASE_URI']})
    assert any(row['id'] == 1 for row in signed(restarted).get('/api/doctors').json['doctors'])


def test_department_change_protects_future_appointments(app):
    admin=signed(app,'Admin'); mutate(signed(app),data=booking())
    response=mutate(admin,'PATCH','/api/admin/doctors/1',{'department':'Cardiology'})
    assert response.status_code == 409
    assert next(row for row in signed(app).get('/api/doctors').json['doctors'] if row['id'] == 1)['department'] == 'General Medicine'


def test_profile_without_account_can_be_deactivated_and_created_inactive(app):
    admin=signed(app,'Admin')
    assert mutate(admin,'PATCH','/api/admin/doctors/3',{'active':False}).status_code == 200
    response=mutate(admin,'POST','/api/admin/doctors',doctor_data(doctor_id=3,name='Dr. Sofia Garcia',department='Pediatrics',active=False))
    assert response.status_code == 201 and response.json['active'] is False
    assert login(app,'newdoctor@test.com','DoctorPass123!')[1].status_code == 400


def test_public_registration_stays_patient_only(app):
    client=app.test_client(); client.get('/register')
    with client.session_transaction() as state: token=state['csrf']
    response=client.post('/register',data=dict(name='Public Doctor Attempt',email='public@test.com',password=PASSWORD,
                                              role='doctor',doctor_id=1,demo_doctor=True,csrf_token=token))
    assert response.status_code == 302 and response.location.endswith('/patient/dashboard')
    assert client.get('/api/admin/doctors').status_code == 403
    with app.app_context():
        user=db.session.scalar(db.select(User).where(User.email == 'public@test.com'))
        assert user.role == 'patient' and user.doctor_id is None and not user.demo_doctor


def test_email_collision_does_not_change_other_profile_details(app):
    response=mutate(signed(app,'Admin'),'PATCH','/api/admin/doctors/1',{'name':'Wrong Name','email':'patientone@test.com'})
    assert response.status_code == 409
    with app.app_context(): assert db.session.get(Doctor,1).name == 'Dr. Maria Santos'


def test_reactivated_legacy_profile_is_not_retired_again_on_restart(app):
    with app.app_context():
        doctor=Doctor(name='Dr. Juan Reyes',department='General Medicine',active=False)
        db.session.add(doctor); db.session.commit(); did=doctor.id
    assert mutate(signed(app,'Admin'),'PATCH',f'/api/admin/doctors/{did}',{'active':True}).status_code == 200
    restarted=create_app({'TESTING':True,'SECRET_KEY':'test-only','SQLALCHEMY_DATABASE_URI':app.config['SQLALCHEMY_DATABASE_URI']})
    with restarted.app_context(): assert db.session.get(Doctor,did).active is True


def test_deactivation_between_booking_validation_and_write_is_respected(app,monkeypatch):
    from app.routes import lock_schedule
    admin=signed(app,'Admin')
    def deactivate_before_lock():
        assert mutate(admin,'PATCH','/api/admin/doctors/1',{'active':False}).status_code == 200
        lock_schedule()
    monkeypatch.setattr('app.routes.lock_schedule',deactivate_before_lock)
    result=mutate(signed(app),data=booking())
    assert result.status_code == 400
    assert admin.get('/api/appointments').json['appointments'] == []


def test_undo_cancellation_does_not_restore_booking_for_inactive_doctor(app):
    patient,admin=signed(app),signed(app,'Admin')
    aid=mutate(patient,data=booking()).json['id']
    cancelled=mutate(patient,'PATCH',f'/api/appointments/{aid}',{'status':'Cancelled'})
    assert mutate(admin,'PATCH','/api/admin/doctors/1',{'active':False}).status_code == 200
    undo=mutate(patient,'POST',f'/api/actions/{cancelled.json["undo"]["token"]}/undo',{})
    assert undo.status_code == 409
    assert patient.get('/api/appointments').json['appointments'][0]['status'] == 'Cancelled'
