from datetime import datetime

import pytest

from app import db
from app.models import Doctor,User,Action
from app.scheduling import default_week
from test_workflows import app,signed,mutate,booking


def undo(client,response):
    return mutate(client,'POST',f'/api/actions/{response.json["undo"]["token"]}/undo')


def test_one_active_doctor_per_department_and_philippine_timezone(app):
    doctors=signed(app).get('/api/doctors').json['doctors']
    assert len(doctors) == 3
    assert len({doctor['department'] for doctor in doctors}) == 3
    assert app.config['HOSPITAL_TIMEZONE'] == 'Asia/Manila'
    assert signed(app,'Doctor One').get('/api/working-hours').json['timezone'] == 'Asia/Manila'


def test_only_demo_doctor_can_switch_and_all_doctor_data_follows_pov(app):
    doctor=signed(app,'Doctor One')
    assert mutate(doctor,'POST','/api/demo/doctor-pov',{'doctor_id':2}).status_code == 403
    with app.app_context():
        user=db.session.scalar(db.select(User).where(User.name == 'Doctor One'))
        user.demo_doctor=True; db.session.commit()
    created=mutate(signed(app),data=booking()).json
    assert doctor.get('/api/appointments').json['appointments'][0]['id'] == created['id']
    assert mutate(doctor,'POST','/api/demo/doctor-pov',{'doctor_id':2}).status_code == 200
    assert doctor.get('/api/appointments').json['appointments'] == []
    assert mutate(doctor,'PATCH',f'/api/appointments/{created["id"]}',{'status':'Cancelled'}).status_code == 403
    assert mutate(doctor,'POST','/api/blocked-dates',{'date':'2030-01-03'}).status_code == 200
    assert signed(app,'Doctor Two').get('/api/blocked-dates').json['dates'] == ['2030-01-03']
    assert mutate(doctor,'POST','/api/demo/doctor-pov',{'doctor_id':1}).status_code == 200
    assert doctor.get('/api/blocked-dates').json['dates'] == []
    assert mutate(signed(app),'POST','/api/demo/doctor-pov',{'doctor_id':2}).status_code == 403


@pytest.mark.parametrize('actor',['Doctor One','Admin'])
def test_completion_only_after_appointment_end(app,monkeypatch,actor):
    patient=signed(app); clinician=signed(app,actor)
    aid=mutate(patient,data=booking()).json['id']
    path=f'/api/appointments/{aid}'
    assert mutate(patient,'PATCH',path,{'status':'Completed'}).status_code == 403
    assert mutate(clinician,'PATCH',path,{'status':'Completed'}).status_code == 409
    assert mutate(clinician,'PATCH',path,{'status':'No-show'}).status_code == 409
    monkeypatch.setattr('app.routes.now',lambda: datetime(2030,1,2,9,59))
    assert mutate(clinician,'PATCH',path,{'status':'Completed'}).status_code == 409
    monkeypatch.setattr('app.routes.now',lambda: datetime(2030,1,2,10,0))
    response=mutate(clinician,'PATCH',path,{'status':'Completed'})
    assert response.status_code == 200
    assert patient.get('/api/appointments').json['appointments'][0]['status'] == 'Completed'
    assert undo(clinician,response).status_code == 200
    assert patient.get('/api/appointments').json['appointments'][0]['status'] == 'Confirmed'


def test_undo_patient_removal_and_cancellation(app):
    patient=signed(app)
    aid=mutate(patient,data=booking()).json['id']
    cancelled=mutate(patient,'PATCH',f'/api/appointments/{aid}',{'status':'Cancelled'})
    removed=mutate(patient,'DELETE',f'/api/appointments/{aid}/patient-list')
    assert patient.get('/api/appointments').json['appointments'] == []
    assert undo(patient,removed).status_code == 200
    assert patient.get('/api/appointments').json['appointments'][0]['status'] == 'Cancelled'
    assert undo(patient,cancelled).status_code == 409
    aid=mutate(patient,data=booking()).json['id']
    second=mutate(patient,'PATCH',f'/api/appointments/{aid}',{'status':'Cancelled'})
    assert undo(patient,second).status_code == 200
    assert undo(patient,second).status_code == 409


def test_undo_booking_keeps_cancelled_hospital_record(app):
    patient=signed(app)
    created=mutate(patient,data=booking())
    assert undo(patient,created).status_code == 200
    assert patient.get('/api/appointments').json['appointments'] == []
    assert signed(app,'Admin').get('/api/appointments').json['appointments'][0]['status'] == 'Cancelled'


def test_undo_is_actor_owned_and_server_expires_after_five_seconds(app,monkeypatch):
    patient=signed(app)
    response=mutate(patient,data=booking())
    assert undo(signed(app,'Patient Two'),response).status_code == 403
    assert undo(signed(app,'Admin'),response).status_code == 403
    monkeypatch.setattr('app.routes.time.time',lambda: response.json['undo']['expires_at'])
    assert undo(patient,response).status_code == 409


def test_undo_cancellation_cannot_displace_new_booking(app):
    patient=signed(app)
    aid=mutate(patient,data=booking()).json['id']
    response=mutate(patient,'PATCH',f'/api/appointments/{aid}',{'status':'Cancelled'})
    assert mutate(signed(app,'Patient Two'),data=booking()).status_code == 201
    assert undo(patient,response).status_code == 409
    assert patient.get('/api/appointments').json['appointments'][0]['status'] == 'Cancelled'


def test_undo_block_and_settings(app):
    doctor=signed(app,'Doctor One')
    blocked=mutate(doctor,'POST','/api/blocked-dates',{'date':'2030-01-03'})
    assert undo(doctor,blocked).status_code == 200
    assert doctor.get('/api/blocked-dates').json['dates'] == []
    week=default_week(); week[2]['start']='10:00'
    saved=mutate(doctor,'PUT','/api/working-hours',{'days':week,'duration_minutes':30})
    assert undo(doctor,saved).status_code == 200
    settings=doctor.get('/api/working-hours').json
    assert settings['days'] == default_week() and settings['duration_minutes'] == 60


def test_undo_settings_cannot_invalidate_new_appointment(app):
    doctor=signed(app,'Doctor One')
    week=default_week(); week[2]['start']='08:00'
    saved=mutate(doctor,'PUT','/api/working-hours',{'days':week})
    data=booking(); data['time']='08:00'
    assert mutate(signed(app),data=data).status_code == 201
    assert undo(doctor,saved).status_code == 409


def test_undo_does_not_overwrite_later_status(app,monkeypatch):
    patient=signed(app); doctor=signed(app,'Doctor One')
    created=mutate(patient,data=booking())
    monkeypatch.setattr('app.routes.now',lambda: datetime(2030,1,2,10,0))
    assert mutate(doctor,'PATCH',f'/api/appointments/{created.json["id"]}',{'status':'Completed'}).status_code == 200
    assert undo(patient,created).status_code == 409


def test_undo_unblock_rejects_new_booking(app):
    doctor=signed(app,'Doctor One')
    mutate(doctor,'POST','/api/blocked-dates',{'date':'2030-01-02'})
    unblocked=mutate(doctor,'DELETE','/api/blocked-dates',{'date':'2030-01-02'})
    assert mutate(signed(app),data=booking()).status_code == 201
    assert undo(doctor,unblocked).status_code == 409


def test_undo_scoped_to_demo_pov(app):
    with app.app_context():
        user=db.session.scalar(db.select(User).where(User.name == 'Doctor One'))
        user.demo_doctor=True; db.session.commit()
    doctor=signed(app,'Doctor One')
    blocked=mutate(doctor,'POST','/api/blocked-dates',{'date':'2030-01-03'})
    mutate(doctor,'POST','/api/demo/doctor-pov',{'doctor_id':2})
    assert undo(doctor,blocked).status_code == 403
    mutate(doctor,'POST','/api/demo/doctor-pov',{'doctor_id':1})
    assert undo(doctor,blocked).status_code == 200


def test_normal_doctor_ignores_demo_session_scope(app):
    created=mutate(signed(app),data=booking()).json
    doctor=signed(app,'Doctor Two')
    with doctor.session_transaction() as session:
        session['demo_doctor_id']=1
    assert doctor.get('/api/appointments').json['appointments'] == []
    assert mutate(doctor,'PATCH',f'/api/appointments/{created["id"]}',{'status':'Cancelled'}).status_code == 403


def test_old_undo_cannot_reverse_a_newer_identical_status(app):
    patient=signed(app)
    aid=mutate(patient,data=booking()).json['id']
    first=mutate(patient,'PATCH',f'/api/appointments/{aid}',{'status':'Cancelled'})
    assert undo(patient,first).status_code == 200
    second=mutate(patient,'PATCH',f'/api/appointments/{aid}',{'status':'Cancelled'})
    assert undo(patient,first).status_code == 409
    assert undo(patient,second).status_code == 200


def test_stale_doctor_tab_cannot_write_to_new_pov(app):
    with app.app_context():
        user=db.session.scalar(db.select(User).where(User.name == 'Doctor One')); user.demo_doctor=True; db.session.commit()
    doctor=signed(app,'Doctor One')
    mutate(doctor,'POST','/api/demo/doctor-pov',{'doctor_id':2})
    assert doctor.get('/api/appointments').json['doctor_id'] == 2
    response=doctor.post('/api/blocked-dates',json={'date':'2030-01-03'},headers={'X-CSRF-Token':'test-token','X-Doctor-Context':'1'})
    assert response.status_code == 409 and response.json['code'] == 'CONTEXT_CHANGED'
    assert doctor.get('/api/blocked-dates').json['dates'] == []


def test_stale_role_tab_does_not_render_another_roles_records(app):
    patient=signed(app)
    response=patient.get('/api/appointments',headers={'X-Portal-Role':'admin'})
    assert response.status_code == 401 and response.json['code'] == 'ROLE_CHANGED'
    assert patient.get('/api/appointments',headers={'X-Portal-Role':'patient'}).status_code == 200


def test_old_block_undo_cannot_reverse_newer_identical_state(app):
    doctor=signed(app,'Doctor One')
    first=mutate(doctor,'POST','/api/blocked-dates',{'date':'2030-01-03'})
    mutate(doctor,'DELETE','/api/blocked-dates',{'date':'2030-01-03'})
    latest=mutate(doctor,'POST','/api/blocked-dates',{'date':'2030-01-03'})
    assert undo(doctor,first).status_code == 409
    assert undo(doctor,latest).status_code == 200
