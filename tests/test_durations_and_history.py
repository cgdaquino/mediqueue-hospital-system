import csv
import io
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app import create_app, db
from app.models import Appointment, Doctor
from app.scheduling import default_week
from test_workflows import app, signed, mutate, booking


def set_duration(client,duration,week=None):
    return mutate(client,'PUT','/api/working-hours',{'days':week or default_week(),'duration_minutes':duration})


@pytest.mark.parametrize('duration,end',[(15,'09:15'),(30,'09:30'),(45,'09:45'),(60,'10:00'),(90,'10:30'),(120,'11:00')])
def test_doctor_duration_drives_booking_and_saved_end_time(app,duration,end):
    doctor,patient=signed(app,'Doctor One'),signed(app)
    assert set_duration(doctor,duration).status_code == 200
    assert doctor.get('/api/working-hours').json['duration_minutes'] == duration
    assert patient.get('/api/availability?doctor_id=1&date=2030-01-02').json['duration_minutes'] == duration
    data=booking(); data['duration_minutes']=duration
    created=mutate(patient,data=data)
    assert created.status_code == 201
    assert (created.json['duration_minutes'],created.json['end_time']) == (duration,end)


@pytest.mark.parametrize('duration',[None,0,10,25,180,True,'30',30.5,[],{}])
def test_invalid_duration_rejected_without_changes(app,duration):
    doctor=signed(app,'Doctor One')
    assert set_duration(doctor,duration).status_code == 400
    assert doctor.get('/api/working-hours').json['duration_minutes'] == 60


def test_duration_changes_keep_existing_bookings_and_use_mixed_overlap_lengths(app):
    doctor,patient=signed(app,'Doctor One'),signed(app)
    first=mutate(patient,data=booking()).json
    assert set_duration(doctor,30).status_code == 200
    assert patient.get('/api/appointments').json['appointments'][0]['end_time'] == '10:00'
    data=booking(); data['time']='09:30'
    assert mutate(patient,data=data).status_code == 409
    data['time']='10:00'
    second=mutate(patient,data=data).json
    assert second['duration_minutes'] == 30 and second['end_time'] == '10:30'
    assert set_duration(doctor,90).status_code == 200
    data['time']='10:30'
    assert mutate(patient,data=data).status_code == 201
    records={row['id']:row for row in patient.get('/api/appointments').json['appointments']}
    assert records[first['id']]['duration_minutes'] == 60
    assert records[second['id']]['duration_minutes'] == 30


def test_existing_long_booking_must_still_fit_when_hours_change(app):
    doctor,patient=signed(app,'Doctor One'),signed(app)
    assert set_duration(doctor,90).status_code == 200
    created=mutate(patient,data=booking()).json
    week=default_week(); week[2].update(end='10:00',lunch_start=None,lunch_end=None)
    response=set_duration(doctor,30,week)
    assert response.status_code == 409 and created['reference'] in response.json['error']


def test_short_durations_fit_break_boundaries_and_reject_stale_patient_length(app):
    doctor,patient=signed(app,'Doctor One'),signed(app)
    assert set_duration(doctor,30).status_code == 200
    available=patient.get('/api/availability?doctor_id=1&date=2030-01-02').json
    assert '11:30' in available['slots'] and '12:00' not in available['slots'] and '16:30' in available['slots']
    data=booking(); data['duration_minutes']=60
    assert mutate(patient,data=data).status_code == 409
    assert patient.get('/api/appointments').json['appointments'] == []
    assert set_duration(doctor,45).status_code == 200
    slots=patient.get('/api/availability?doctor_id=1&date=2030-01-02').json['slots']
    assert '11:15' in slots and '11:30' not in slots and '16:15' in slots and '16:30' not in slots


def test_cancellation_and_patient_only_removal_preserve_staff_history(app):
    patient,doctor,admin=signed(app),signed(app,'Doctor One'),signed(app,'Admin')
    aid=mutate(patient,data=booking()).json['id']
    assert mutate(patient,'DELETE',f'/api/appointments/{aid}/patient-list').status_code == 409
    assert mutate(patient,'PATCH',f'/api/appointments/{aid}',{'status':'Cancelled'}).status_code == 200
    for staff in (doctor,admin):
        assert staff.get('/api/appointments').json['appointments'][0]['status'] == 'Cancelled'
    assert mutate(patient,'DELETE',f'/api/appointments/{aid}/patient-list').status_code == 200
    assert mutate(patient,'DELETE',f'/api/appointments/{aid}/patient-list').status_code == 200
    assert patient.get('/api/appointments').json['appointments'] == []
    for staff in (doctor,admin):
        assert staff.get('/api/appointments').json['appointments'][0]['id'] == aid
    report=list(csv.DictReader(io.StringIO(admin.get('/api/reports/appointments.csv').data.decode('utf-8-sig'))))
    assert report[0]['Status'] == 'Cancelled'
    assert '09:00' in patient.get('/api/availability?doctor_id=1&date=2030-01-02').json['slots']
    assert mutate(patient,data=booking()).status_code == 201


def test_only_owner_can_hide_and_only_cancelled_records(app):
    patient,other=signed(app),signed(app,'Patient Two')
    aid=mutate(patient,data=booking()).json['id']
    assert mutate(patient,'PATCH',f'/api/appointments/{aid}',{'status':'Cancelled'}).status_code == 200
    for client in (other,signed(app,'Doctor One'),signed(app,'Admin')):
        assert mutate(client,'DELETE',f'/api/appointments/{aid}/patient-list').status_code == 403
    assert patient.delete(f'/api/appointments/{aid}/patient-list').status_code == 400
    assert mutate(patient,'DELETE','/api/appointments/999/patient-list').status_code == 404


def test_staff_cancellation_can_be_hidden_and_persists_after_restart(app):
    patient,admin=signed(app),signed(app,'Admin')
    aid=mutate(patient,data=booking()).json['id']
    assert mutate(admin,'PATCH',f'/api/appointments/{aid}',{'status':'Cancelled'}).status_code == 200
    assert mutate(patient,'DELETE',f'/api/appointments/{aid}/patient-list').status_code == 200
    assert set_duration(signed(app,'Doctor One'),45).status_code == 200
    restarted=create_app({'TESTING':True,'SECRET_KEY':'test-only','SQLALCHEMY_DATABASE_URI':app.config['SQLALCHEMY_DATABASE_URI']})
    assert signed(restarted).get('/api/appointments').json['appointments'] == []
    assert signed(restarted,'Admin').get('/api/appointments').json['appointments'][0]['status'] == 'Cancelled'
    assert signed(restarted,'Doctor One').get('/api/working-hours').json['duration_minutes'] == 45


def test_duration_change_and_booking_are_consistent(app):
    doctor,patient=signed(app,'Doctor One'),signed(app)
    barrier=Barrier(2)
    def attempt(action):
        barrier.wait()
        if action == 'duration':
            return set_duration(doctor,30).status_code
        data=booking(); data['duration_minutes']=60
        return mutate(patient,data=data).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(attempt,['duration','book']))
    assert responses in ([200,201],[200,409])
    records=patient.get('/api/appointments').json['appointments']
    if records:
        assert records[0]['duration_minutes'] == 60


def test_existing_sqlite_data_is_upgraded_without_losing_appointments(tmp_path):
    path=tmp_path/'legacy.db'
    with sqlite3.connect(path) as conn:
        conn.executescript('''
        CREATE TABLE doctor (id INTEGER PRIMARY KEY,name VARCHAR(120) NOT NULL,department VARCHAR(80) NOT NULL);
        CREATE TABLE appointment (id INTEGER PRIMARY KEY,patient VARCHAR(120) NOT NULL,patient_id INTEGER,
          doctor_id INTEGER NOT NULL,date VARCHAR(10) NOT NULL,time VARCHAR(5) NOT NULL,status VARCHAR(20) NOT NULL,type VARCHAR(20) NOT NULL);
        INSERT INTO doctor VALUES (1,'Legacy Doctor','General Medicine');
        INSERT INTO appointment VALUES (1,'Legacy Patient',NULL,1,'2030-01-02','09:00','Cancelled','Walk-in');
        ''')
    config={'TESTING':True,'SECRET_KEY':'test-only','SQLALCHEMY_DATABASE_URI':f'sqlite:///{path.as_posix()}'}
    for _ in range(2):
        migrated=create_app(config)
        with migrated.app_context():
            record=db.session.get(Appointment,1)
            assert record.patient == 'Legacy Patient' and record.status == 'Cancelled'
            assert record.duration_minutes == 60 and record.patient_hidden is False
            assert db.session.get(Doctor,1).duration_minutes == 60
