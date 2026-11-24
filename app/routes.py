import csv
import hmac
import io
import secrets
import time
from datetime import date, datetime
from functools import wraps
from zoneinfo import ZoneInfo

import click
from flask import (Blueprint, Response, abort, current_app, g, redirect,
                   render_template, request, session, url_for)
from flask.cli import with_appcontext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .models import Appointment, BlockedDate, Doctor, User, WeeklyAvailability, Action
from .actions import remember, appointment_state, settings_state
from .registration import validate_patient_registration
from .scheduling import overlaps, schedule_slots, fits_schedule, validate_week, time_minutes, valid_duration, DURATION_OPTIONS

bp = Blueprint('portal', __name__)


def current_doctor_id():
    return session.get('demo_doctor_id',g.user.doctor_id) if g.user.demo_doctor else g.user.doctor_id


def now():
    return datetime.now(ZoneInfo(current_app.config['HOSPITAL_TIMEZONE'])).replace(tzinfo=None)


def token():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_hex(32)
    return session['csrf']


@bp.app_context_processor
def context():
    return {'csrf_token': token, 'current_user': getattr(g, 'user', None)}


@bp.before_app_request
def load_user_and_check_csrf():
    g.user = db.session.get(User, session.get('user_id')) if session.get('user_id') else None
    invalid=False
    if g.user:
        invalid=not g.user.enabled or session.get('auth_version',0) != g.user.auth_version
        if g.user.role == 'doctor':
            own=db.session.get(Doctor,g.user.doctor_id)
            invalid=invalid or not own or not own.active
        if invalid:
            session.clear(); g.user=None
        elif g.user.demo_doctor and session.get('demo_doctor_id'):
            selected=db.session.get(Doctor,session['demo_doctor_id'])
            if not selected or not selected.active:
                session.pop('demo_doctor_id',None)
    if invalid and request.path.startswith('/api/') and request.path != '/api/health':
        return {'error':'Your account changed or was deactivated. Please sign in again.'},401
    portal_role=request.headers.get('X-Portal-Role')
    if g.user and portal_role and request.path.startswith('/api/') and portal_role != g.user.role:
        return {'error':'The signed-in account changed in another tab. Sign in for this portal again.','code':'ROLE_CHANGED'},401
    context=request.headers.get('X-Doctor-Context')
    if g.user and g.user.role == 'doctor' and context and request.method in ('POST','PATCH','DELETE','PUT') and request.path != '/api/demo/doctor-pov':
        if context != str(current_doctor_id()):
            return {'error':'The demo doctor POV changed in another tab. Refresh before making changes.','code':'CONTEXT_CHANGED'},409
    if request.method in ('POST', 'PATCH', 'DELETE', 'PUT'):
        provided = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token', '')
        expected = session.get('csrf', '')
        if not expected or not hmac.compare_digest(expected.encode(), provided.encode()):
            return {'error': 'Your session expired. Refresh the page and try again.'}, 400


def roles(*allowed):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not g.user:
                if request.path.startswith('/api/'):
                    return {'error': 'Please sign in.'}, 401
                return redirect(url_for('portal.login'))
            if g.user.role not in allowed:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return decorator


def payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError('Send a JSON object.')
    return data


@bp.app_errorhandler(ValueError)
def invalid(error):
    return {'error': str(error)}, 400


@bp.app_errorhandler(403)
def forbidden(error):
    return {'error': 'You do not have permission to access this resource.'}, 403


def valid_date(value):
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError()
        return parsed
    except (ValueError, TypeError):
        raise ValueError('Select a valid date (YYYY-MM-DD).')


def doctor_by_id(value):
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit() or len(str(value)) > 9:
        raise ValueError('Select a valid doctor.')
    doctor = db.session.get(Doctor, int(value))
    if not doctor or not doctor.active:
        raise ValueError('Select a valid doctor.')
    return doctor


def lock_schedule():
    # Serialize booking/block decisions, including between separate Flask workers.
    db.session.rollback()
    db.session.execute(text('BEGIN IMMEDIATE'))


@bp.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = db.session.scalar(db.select(User).filter_by(email=email))
        enabled=user and user.enabled and (user.role != 'doctor' or (db.session.get(Doctor,user.doctor_id) and db.session.get(Doctor,user.doctor_id).active))
        if enabled and check_password_hash(user.password_hash, request.form.get('password', '')):
            session.clear()
            session['user_id'] = user.id
            session['auth_version']=user.auth_version
            token()
            return redirect(url_for(f'portal.{user.role}_dashboard'))
        error = 'Incorrect email or password.'
    return render_template('auth.html', register=False, error=error), 400 if error else 200


@bp.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        try:
            name,email,password=validate_patient_registration(name,email,password)
        except ValueError as exc:
            error=str(exc)
        else:
            user = User(name=name, email=email, password_hash=generate_password_hash(password), role='patient')
            db.session.add(user)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                error = 'That email is already registered.'
            else:
                session.clear()
                session['user_id'] = user.id
                token()
                return redirect(url_for('portal.patient_dashboard'))
    return render_template('auth.html', register=True, error=error), 400 if error else 200


@bp.post('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


@bp.get('/patient/dashboard')
@roles('patient')
def patient_dashboard():
    return render_template('patient/dashboard.html')


@bp.get('/doctor/dashboard')
@roles('doctor')
def doctor_dashboard():
    return render_template('doctor/dashboard.html',doctor=db.session.get(Doctor,current_doctor_id()),
                           demo_doctors=list(db.session.scalars(db.select(Doctor).where(Doctor.active.is_(True)).order_by(Doctor.id))) if g.user.demo_doctor else [])


@bp.post('/api/demo/doctor-pov')
@roles('doctor')
def demo_doctor_pov():
    if not g.user.demo_doctor:
        abort(403)
    doctor=doctor_by_id(payload().get('doctor_id'))
    session['demo_doctor_id']=doctor.id
    return {'doctor_id':doctor.id,'name':doctor.name}


@bp.get('/admin/dashboard')
@roles('admin')
def admin_dashboard():
    return render_template('admin/dashboard.html')


@bp.get('/api/doctors')
@roles('patient', 'doctor', 'admin')
def doctors():
    return {'doctors': [dict(id=d.id, name=d.name, department=d.department)
                        for d in db.session.scalars(db.select(Doctor).where(Doctor.active.is_(True)).order_by(Doctor.id))],
            'today': now().date().isoformat()}


@bp.get('/api/availability')
@roles('patient', 'admin')
def availability():
    doctor = doctor_by_id(request.args.get('doctor_id'))
    day = request.args.get('date')
    parsed_day = valid_date(day)
    schedule = db.session.scalar(db.select(WeeklyAvailability).filter_by(doctor_id=doctor.id,weekday=parsed_day.weekday())).as_dict()
    blocked = db.session.scalar(db.select(BlockedDate.id).filter_by(doctor_id=doctor.id, date=day))
    taken = list(db.session.execute(db.select(Appointment.time,Appointment.duration_minutes).where(
        Appointment.doctor_id == doctor.id, Appointment.date == day, Appointment.status != 'Cancelled')))
    duration=doctor.duration_minutes
    slots = [] if blocked else [t for t in schedule_slots(schedule,duration) if not any(overlaps(t, occupied,duration,length) for occupied,length in taken)
                               and datetime.fromisoformat(f'{day}T{t}') > now()]
    reason = 'This doctor has blocked this date. Please choose another date.' if blocked else (
        'This doctor does not work on this day. Please choose another date.' if not schedule['enabled'] else '')
    return {'slots': slots, 'blocked': bool(blocked), 'reason':reason, 'schedule':schedule, 'duration_minutes':duration}


def visible_appointments():
    query = db.select(Appointment)
    if g.user.role == 'patient':
        query = query.where(Appointment.patient_id == g.user.id,Appointment.patient_hidden.is_(False))
    elif g.user.role == 'doctor':
        query = query.where(Appointment.doctor_id == current_doctor_id())
    return query.order_by(Appointment.date, Appointment.time, Appointment.id)


@bp.get('/api/appointments')
@roles('patient', 'doctor', 'admin')
def appointments():
    result={'appointments': [a.as_dict() for a in db.session.scalars(visible_appointments())], 'now': now().isoformat()}
    if g.user.role == 'doctor':
        result['doctor_id']=current_doctor_id()
    return result


@bp.post('/api/appointments')
@roles('patient', 'admin')
def book():
    data = payload()
    patient_id = g.user.id if g.user.role == 'patient' else None
    patient = g.user.name if patient_id else data.get('patient', '')
    if not isinstance(patient, str) or not patient.strip() or len(patient.strip()) > 120:
        raise ValueError('Enter a patient name (1–120 characters).')
    doctor_id = doctor_by_id(data.get('doctor_id')).id
    day, slot = data.get('date'), data.get('time')
    parsed_day = valid_date(day)
    # Basic time validation happens before taking the scheduling write lock.
    time_minutes(slot)
    if datetime.fromisoformat(f'{day}T{slot}') <= now():
        raise ValueError('Appointments must be in the future.')
    lock_schedule()
    # Recheck inside the write lock: admin deactivation may have won the race.
    doctor_by_id(doctor_id)
    if db.session.scalar(db.select(BlockedDate.id).filter_by(doctor_id=doctor_id, date=day)):
        return {'error': 'This doctor has blocked this date. Please choose another date.', 'code':'DATE_UNAVAILABLE'}, 409
    schedule = db.session.scalar(db.select(WeeklyAvailability).filter_by(doctor_id=doctor_id,weekday=parsed_day.weekday())).as_dict()
    duration=db.session.get(Doctor,doctor_id).duration_minutes
    if data.get('duration_minutes',duration) != duration:
        return {'error':'The doctor changed the appointment duration. Refresh the available times and choose again.','code':'SCHEDULE_CHANGED'},409
    if slot not in schedule_slots(schedule,duration):
        return {'error':'Choose a full appointment within the doctor’s working hours, outside lunch.', 'code':'SCHEDULE_CHANGED'}, 409
    occupied = db.session.execute(db.select(Appointment.time,Appointment.duration_minutes).where(
        Appointment.doctor_id == doctor_id, Appointment.date == day, Appointment.status != 'Cancelled'))
    if any(overlaps(slot,start,duration,length) for start,length in occupied):
        return {'error': 'This appointment overlaps another booking. Choose another time.'}, 409
    appointment = Appointment(patient=patient.strip(), patient_id=patient_id, doctor_id=doctor_id,
                              date=day, time=slot, duration_minutes=duration, type='Online' if patient_id else 'Walk-in')
    db.session.add(appointment)
    try:
        db.session.flush()
        undo=remember(g.user.id,'create',appointment.id,None,appointment_state(appointment))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {'error': 'This time slot is already booked. Choose another time.'}, 409
    return dict(appointment.as_dict(),undo=undo,action_message='Appointment booked.'), 201


@bp.patch('/api/appointments/<int:appointment_id>')
@roles('patient', 'doctor', 'admin')
def update_appointment(appointment_id):
    status = payload().get('status')
    appointment = db.session.get(Appointment, appointment_id)
    if not appointment:
        return {'error': 'Appointment not found.'}, 404
    if g.user.role == 'patient':
        if appointment.patient_id != g.user.id or status != 'Cancelled':
            abort(403)
        if datetime.fromisoformat(f'{appointment.date}T{appointment.time}') <= now():
            return {'error': 'Past appointments cannot be cancelled.'}, 409
    elif g.user.role == 'doctor':
        if appointment.doctor_id != current_doctor_id() or status not in ('Completed', 'No-show','Cancelled'):
            abort(403)
    elif status not in ('Completed', 'No-show', 'Cancelled'):
        raise ValueError('Select a valid status.')
    start=datetime.fromisoformat(f'{appointment.date}T{appointment.time}')
    from datetime import timedelta
    if status == 'Completed' and now() < start+timedelta(minutes=appointment.duration_minutes):
        return {'error':'A doctor or administrator can mark completion after the appointment ends.'},409
    if status == 'No-show' and now() < start:
        return {'error':'No-show can be recorded after the appointment starts.'},409
    before=appointment_state(appointment)
    result = db.session.execute(db.update(Appointment).where(
        Appointment.id == appointment_id, Appointment.status == 'Confirmed').values(status=status,version=Appointment.version+1))
    if result.rowcount != 1:
        db.session.rollback()
        return {'error': 'Only confirmed appointments can be changed. Refresh the page.'}, 409
    undo=remember(g.user.id,'status',appointment.id,before,appointment_state(appointment),current_doctor_id() if g.user.role == 'doctor' else None)
    db.session.commit()
    return dict(db.session.get(Appointment, appointment_id).as_dict(),undo=undo,action_message=f'Appointment marked {status.lower()}.')


@bp.delete('/api/appointments/<int:appointment_id>/patient-list')
@roles('patient')
def hide_cancelled_appointment(appointment_id):
    appointment=db.session.get(Appointment,appointment_id)
    if not appointment:
        return {'error':'Appointment not found.'},404
    if appointment.patient_id != g.user.id:
        abort(403)
    if appointment.status != 'Cancelled':
        return {'error':'Only cancelled appointments can be removed from your list.'},409
    if appointment.patient_hidden:
        return {'hidden':True}
    before=appointment_state(appointment)
    appointment.patient_hidden=True
    appointment.version+=1
    undo=remember(g.user.id,'hide',appointment.id,before,appointment_state(appointment))
    db.session.commit()
    return {'hidden':True,'undo':undo,'action_message':'Removed from your list. Hospital history is retained.'}


@bp.route('/api/blocked-dates', methods=['GET', 'POST', 'DELETE'])
@roles('doctor')
def blocked_dates():
    doctor_id = current_doctor_id()
    undo=None
    if request.method != 'GET':
        day = payload().get('date')
        if valid_date(day) < now().date() and request.method == 'POST':
            raise ValueError('Select today or a future date.')
        lock_schedule()
        before=bool(db.session.scalar(db.select(BlockedDate.id).filter_by(doctor_id=doctor_id,date=day)))
        if request.method == 'POST':
            conflict = db.session.scalar(db.select(Appointment.id).where(
                Appointment.doctor_id == doctor_id, Appointment.date == day,
                Appointment.status == 'Confirmed').limit(1))
            if conflict:
                return {'error': 'This date has confirmed appointments. Resolve them before blocking it.'}, 409
            if not db.session.scalar(db.select(BlockedDate.id).filter_by(doctor_id=doctor_id, date=day)):
                db.session.add(BlockedDate(doctor_id=doctor_id, date=day))
        else:
            db.session.execute(db.delete(BlockedDate).where(BlockedDate.doctor_id == doctor_id, BlockedDate.date == day))
        after=request.method == 'POST'
        if before != after:
            undo=remember(g.user.id,'block',None,{'date':day,'blocked':before},{'date':day,'blocked':after},doctor_id)
        db.session.commit()
    result={'dates': list(db.session.scalars(db.select(BlockedDate.date).filter_by(doctor_id=doctor_id).order_by(BlockedDate.date))),'doctor_id':doctor_id}
    if undo:
        result.update(undo=undo,action_message='Unavailable date saved.' if after else 'Date unblocked.')
    return result


@bp.route('/api/working-hours',methods=['GET','PUT'])
@roles('doctor')
def working_hours():
    doctor_id = current_doctor_id()
    undo=None
    if request.method == 'PUT':
        data=payload()
        lock_schedule()
        doctor=db.session.get(Doctor,doctor_id)
        before=settings_state(doctor)
        duration=valid_duration(data.get('duration_minutes',doctor.duration_minutes))
        week = validate_week(data.get('days'),duration)
        future = db.session.scalars(db.select(Appointment).where(
            Appointment.doctor_id == doctor_id,Appointment.status == 'Confirmed',Appointment.date >= now().date().isoformat()))
        for appointment in future:
            if datetime.fromisoformat(f'{appointment.date}T{appointment.time}') > now() and not fits_schedule(
                    appointment.time,week[date.fromisoformat(appointment.date).weekday()],appointment.duration_minutes):
                return {'error':f'{appointment.as_dict()["reference"]} on {appointment.date} at {appointment.time} conflicts with these hours. Resolve that confirmed booking before saving.'},409
        for day in week:
            db.session.execute(db.update(WeeklyAvailability).where(
                WeeklyAvailability.doctor_id == doctor_id,WeeklyAvailability.weekday == day['weekday']).values(**day))
        doctor.duration_minutes=duration
        doctor.settings_version+=1
        undo=remember(g.user.id,'settings',None,before,{'days':week,'duration_minutes':duration,'version':doctor.settings_version},doctor_id)
        db.session.commit()
    result={'days':[row.as_dict() for row in db.session.scalars(db.select(WeeklyAvailability).filter_by(doctor_id=doctor_id).order_by(WeeklyAvailability.weekday))],
            'duration_minutes':db.session.get(Doctor,doctor_id).duration_minutes,'duration_options':list(DURATION_OPTIONS),'timezone':current_app.config['HOSPITAL_TIMEZONE'],'doctor_id':doctor_id}
    if undo:
        result.update(undo=undo,action_message='Availability and duration saved.')
    return result


@bp.get('/api/reports/appointments.csv')
@roles('admin')
def export_csv():
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['Patient', 'Doctor', 'Date', 'Start Time', 'End Time', 'Duration (minutes)', 'Status', 'Type'])
    def safe(value):
        value = str(value)
        return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')) else value
    for appointment in db.session.scalars(visible_appointments()):
        a = appointment.as_dict()
        writer.writerow([safe(a[k]) for k in ('patient', 'doctor', 'date', 'time', 'end_time', 'duration_minutes', 'status', 'type')])
    return Response('\ufeff' + output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=mediqueue-appointments.csv'})


def restore_slot_allowed(appointment):
    doctor=db.session.get(Doctor,appointment.doctor_id)
    if not doctor or not doctor.active:
        return False
    if db.session.scalar(db.select(BlockedDate.id).filter_by(doctor_id=appointment.doctor_id,date=appointment.date)):
        return False
    row=db.session.scalar(db.select(WeeklyAvailability).filter_by(
        doctor_id=appointment.doctor_id,weekday=date.fromisoformat(appointment.date).weekday()))
    if not row or not fits_schedule(appointment.time,row.as_dict(),appointment.duration_minutes):
        return False
    others=db.session.execute(db.select(Appointment.time,Appointment.duration_minutes).where(
        Appointment.id != appointment.id,Appointment.doctor_id == appointment.doctor_id,
        Appointment.date == appointment.date,Appointment.status != 'Cancelled'))
    return not any(overlaps(appointment.time,start,appointment.duration_minutes,length) for start,length in others)


@bp.post('/api/actions/<action_token>/undo')
@roles('patient','doctor','admin')
def undo_action(action_token):
    actor_id=g.user.id
    doctor_scope=current_doctor_id() if g.user.role == 'doctor' else None
    lock_schedule()
    action=db.session.get(Action,action_token)
    if not action:
        return {'error':'Action not found.'},404
    if action.user_id != actor_id or (action.doctor_id is not None and doctor_scope != action.doctor_id):
        abort(403)
    if action.used or time.time() >= action.expires_at:
        return {'error':'The five-second undo window has ended.'},409
    conflict={'error':'This record changed or the time is no longer available. Refresh to see its current state.'}
    if action.kind in ('create','status','hide'):
        appointment=db.session.get(Appointment,action.target_id)
        if not appointment or appointment_state(appointment) != action.after:
            return conflict,409
        if action.kind == 'create':
            if g.user.role == 'patient' and datetime.fromisoformat(f'{appointment.date}T{appointment.time}') <= now():
                return conflict,409
            appointment.status='Cancelled'
            appointment.patient_hidden=g.user.role == 'patient'
        elif action.kind == 'hide':
            appointment.patient_hidden=action.before['patient_hidden']
        else:
            if action.before['status'] == 'Confirmed':
                if not restore_slot_allowed(appointment):
                    return conflict,409
                if g.user.role == 'patient' and datetime.fromisoformat(f'{appointment.date}T{appointment.time}') <= now():
                    return conflict,409
            appointment.status=action.before['status']
        appointment.version+=1
    elif action.kind == 'block':
        day=action.after['date']
        later=db.session.scalars(db.select(Action).where(Action.kind == 'block',Action.doctor_id == action.doctor_id,Action.expires_at > action.expires_at))
        if any(item.after['date'] == day for item in later):
            return conflict,409
        block=db.session.scalar(db.select(BlockedDate).filter_by(doctor_id=action.doctor_id,date=day))
        if bool(block) != action.after['blocked']:
            return conflict,409
        if action.before['blocked']:
            if db.session.scalar(db.select(Appointment.id).where(Appointment.doctor_id == action.doctor_id,
                Appointment.date == day,Appointment.status == 'Confirmed').limit(1)):
                return conflict,409
            db.session.add(BlockedDate(doctor_id=action.doctor_id,date=day))
        elif block:
            db.session.delete(block)
    elif action.kind == 'settings':
        doctor=db.session.get(Doctor,action.doctor_id)
        if settings_state(doctor) != action.after:
            return conflict,409
        future=db.session.scalars(db.select(Appointment).where(Appointment.doctor_id == doctor.id,
            Appointment.status == 'Confirmed',Appointment.date >= now().date().isoformat()))
        for appointment in future:
            if datetime.fromisoformat(f'{appointment.date}T{appointment.time}') > now() and not fits_schedule(
                appointment.time,action.before['days'][date.fromisoformat(appointment.date).weekday()],appointment.duration_minutes):
                return conflict,409
        doctor.duration_minutes=action.before['duration_minutes']
        doctor.settings_version+=1
        for day in action.before['days']:
            db.session.execute(db.update(WeeklyAvailability).where(
                WeeklyAvailability.doctor_id == doctor.id,WeeklyAvailability.weekday == day['weekday']).values(**day))
    else:
        return {'error':'This action cannot be undone.'},400
    action.used=True
    db.session.commit()
    return {'action_message':'Action undone.','undone':True}


@click.command('seed-demo')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
@with_appcontext
def seed_demo(password):
    """Create local demo accounts explicitly; never replace existing users."""
    if len(password) < 8:
        raise click.ClickException('Use at least 8 characters.')
    doctor = db.session.scalar(db.select(Doctor).filter_by(name='Dr. Maria Santos'))
    for role, name in [('patient', 'Demo Patient'), ('doctor', doctor.name), ('admin', 'Demo Administrator')]:
        email = f'{role}@mediqueue.test'
        if not db.session.scalar(db.select(User.id).filter_by(email=email)):
            if role == 'doctor' and db.session.scalar(db.select(User.id).filter_by(doctor_id=doctor.id)):
                click.echo('Doctor already has an account; keeping that account unchanged.')
                continue
            db.session.add(User(name=name, email=email, role=role,
                                password_hash=generate_password_hash(password),
                                doctor_id=doctor.id if role == 'doctor' else None,demo_doctor=role == 'doctor'))
        elif role == 'doctor':
            existing=db.session.scalar(db.select(User).filter_by(email=email,role='doctor'))
            if existing:
                existing.demo_doctor=True
    db.session.commit()
    click.echo('Demo setup complete. Existing accounts and passwords were kept unchanged.')
