from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app import create_app
from app.scheduling import default_week
from test_workflows import app, signed, mutate, booking


def save(client, days):
    return mutate(client,'PUT','/api/working-hours',{'days':days})


def test_saved_hours_control_patient_and_walkin_booking(app):
    doctor, patient, admin = signed(app,'Doctor One'), signed(app), signed(app,'Admin')
    week = default_week()
    week[2].update(start='08:00',end='16:00',lunch_start='11:00',lunch_end='12:30')
    assert save(doctor,week).status_code == 200
    available = patient.get('/api/availability?doctor_id=1&date=2030-01-02').json
    assert available['slots'] == ['08:00','08:30','09:00','09:30','10:00','12:30','13:00','13:30','14:00','14:30','15:00']
    for start in ('07:30','10:30','11:00','11:30','12:00','15:30','16:00'):
        data = booking(patient='Walk In'); data['time'] = start
        assert mutate(admin,data=data).status_code == 409
    data=booking(); data['time']='12:30'
    assert mutate(patient,data=data).status_code == 201


def test_closed_weekday_and_no_lunch(app):
    doctor,patient = signed(app,'Doctor One'),signed(app)
    week=default_week(); week[2]['enabled']=False
    assert save(doctor,week).status_code == 200
    available=patient.get('/api/availability?doctor_id=1&date=2030-01-02').json
    assert available['slots'] == [] and 'does not work' in available['reason']
    assert mutate(patient,data=booking()).status_code == 409
    week[2].update(enabled=True,lunch_start=None,lunch_end=None)
    assert save(doctor,week).status_code == 200
    assert '12:00' in patient.get('/api/availability?doctor_id=1&date=2030-01-02').json['slots']


def test_default_weekends_closed_and_doctor_can_open_them(app):
    doctor,patient = signed(app,'Doctor One'),signed(app)
    path='/api/availability?doctor_id=1&date=2030-01-05'
    assert patient.get(path).json['slots'] == []
    week=default_week(); week[5]['enabled']=True
    assert save(doctor,week).status_code == 200
    assert '09:00' in patient.get(path).json['slots']


@pytest.mark.parametrize('changes',[
    {'start':'17:00','end':'09:00'}, {'start':'09:10'}, {'start':None},
    {'lunch_start':'11:00','lunch_end':None}, {'lunch_start':'08:00'},
    {'lunch_start':'13:00','lunch_end':'12:00'}, {'end':'09:30','lunch_start':None,'lunch_end':None},
    {'lunch_start':'09:00','lunch_end':'17:00'}, {'enabled':'true'},
])
def test_invalid_schedule_rejected_without_changing_saved_hours(app,changes):
    doctor=signed(app,'Doctor One'); week=default_week(); week[2].update(changes)
    assert save(doctor,week).status_code == 400
    assert doctor.get('/api/working-hours').json['days'] == default_week()


def test_incomplete_or_duplicate_days_rejected(app):
    doctor=signed(app,'Doctor One')
    for week in [[],default_week()[:6],None,[default_week()[0]]*7]:
        assert save(doctor,week).status_code == 400


def test_hours_cannot_displace_existing_confirmed_booking(app):
    doctor,patient=signed(app,'Doctor One'),signed(app)
    appointment=mutate(patient,data=booking()).json
    for changes in [{'enabled':False},{'start':'10:00'},{'lunch_start':'09:00','lunch_end':'10:00'}]:
        week=default_week(); week[2].update(changes)
        response=save(doctor,week)
        assert response.status_code == 409
        assert appointment['reference'] in response.json['error']
    assert doctor.get('/api/working-hours').json['days'] == default_week()
    assert mutate(patient,'PATCH',f'/api/appointments/{appointment["id"]}',{'status':'Cancelled'}).status_code == 200
    week=default_week(); week[2]['enabled']=False
    assert save(doctor,week).status_code == 200


def test_hours_are_private_to_assigned_doctor_and_persist(app):
    doctor,other,patient=signed(app,'Doctor One'),signed(app,'Doctor Two'),signed(app)
    assert patient.get('/api/working-hours').status_code == 403
    assert save(patient,default_week()).status_code == 403
    assert save(signed(app,'Admin'),default_week()).status_code == 403
    week=default_week(); week[2].update(start='10:00')
    assert save(doctor,week).status_code == 200
    assert other.get('/api/working-hours').json['days'] == default_week()
    restarted=create_app({'TESTING':True,'SECRET_KEY':'test-only','SQLALCHEMY_DATABASE_URI':app.config['SQLALCHEMY_DATABASE_URI']})
    assert signed(restarted,'Doctor One').get('/api/working-hours').json['days'] == week


def test_schedule_update_and_booking_are_serialized(app):
    doctor,patient=signed(app,'Doctor One'),signed(app)
    week=default_week(); week[2]['enabled']=False
    barrier=Barrier(2)
    def attempt(action):
        barrier.wait()
        return mutate(patient,data=booking()).status_code if action == 'book' else save(doctor,week).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        result=list(pool.map(attempt,['book','save']))
    assert result in ([201,409],[409,200])


def test_blocked_dates_override_weekly_hours(app):
    doctor,patient=signed(app,'Doctor One'),signed(app)
    assert mutate(doctor,'POST','/api/blocked-dates',{'date':'2030-01-02'}).status_code == 200
    assert save(doctor,default_week()).status_code == 200
    result=patient.get('/api/availability?doctor_id=1&date=2030-01-02').json
    assert result['slots'] == [] and result['blocked'] and 'blocked' in result['reason']


def test_patient_date_warning_is_attached_to_date_field(app):
    html=signed(app).get('/patient/dashboard').data.decode()
    assert 'aria-describedby="dateWarning doctorHours"' in html
    assert html.index('id="date"') < html.index('id="dateWarning"') < html.index('id="time"')
