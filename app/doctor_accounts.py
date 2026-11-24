import re

from flask import Blueprint, request
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from . import db
from .models import Appointment, Doctor, User, WeeklyAvailability
from .routes import roles, payload, lock_schedule, now
from .scheduling import default_week

accounts_bp=Blueprint('doctor_accounts',__name__)
DEPARTMENTS=('General Medicine','Cardiology','Pediatrics')


def fields(data,creating=False):
    allowed={'name','email','department','password','active'} | ({'doctor_id'} if creating else set())
    if set(data)-allowed:
        raise ValueError('Only doctor profile, login, and active-status fields can be changed.')
    values={}
    for key,limit in [('name',120),('email',254)]:
        if key in data or creating:
            value=data.get(key)
            if not isinstance(value,str) or not value.strip() or len(value.strip()) > limit:
                raise ValueError(f'Enter a valid doctor {key}.')
            values[key]=value.strip().lower() if key == 'email' else value.strip()
    if 'email' in values and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',values['email']):
        raise ValueError('Enter a valid email address.')
    if 'department' in data or creating:
        if data.get('department') not in DEPARTMENTS:
            raise ValueError('Select General Medicine, Cardiology, or Pediatrics.')
        values['department']=data['department']
    if 'active' in data:
        if type(data['active']) is not bool:
            raise ValueError('Active status must be true or false.')
        values['active']=data['active']
    password=data.get('password')
    if creating or password not in (None,''):
        if not isinstance(password,str) or not 8 <= len(password) <= 128:
            raise ValueError('Use a password of 8–128 characters.')
        values['password_hash']=generate_password_hash(password)
    return values


def future_count(doctor_id):
    records=db.session.scalars(db.select(Appointment).where(Appointment.doctor_id == doctor_id,Appointment.status == 'Confirmed',Appointment.date >= now().date().isoformat()))
    return sum(f'{row.date}T{row.time}:00' > now().isoformat() for row in records)


def account_json(doctor,user):
    return dict(doctor_id=doctor.id,name=doctor.name,department=doctor.department,
                active=doctor.active,has_account=user is not None,email=user.email if user else '',
                is_demo=user.demo_doctor if user else False,future_confirmed=future_count(doctor.id))


def profile_id(value):
    if isinstance(value,bool) or not str(value).isascii() or not str(value).isdigit() or len(str(value)) > 9:
        raise ValueError('Select a valid existing doctor profile.')
    return int(value)


def department_conflict(doctor,new_department):
    return new_department != doctor.department and future_count(doctor.id) > 0


@accounts_bp.route('/api/admin/doctors',methods=['GET','POST'])
@roles('admin')
def doctors():
    if request.method == 'GET':
        rows=db.session.execute(db.select(Doctor,User).outerjoin(User,User.doctor_id == Doctor.id).order_by(Doctor.name))
        return {'doctors':[account_json(doctor,user) for doctor,user in rows], 'departments':list(DEPARTMENTS)}
    data=payload(); values=fields(data,creating=True)
    existing_id=data.get('doctor_id')
    existing_id=profile_id(existing_id) if existing_id is not None else None
    lock_schedule()
    if db.session.scalar(db.select(User.id).where(User.email == values['email'])):
        return {'error':'That email address is already registered.'},409
    if existing_id is not None:
        doctor=db.session.get(Doctor,existing_id)
        if not doctor:
            return {'error':'Doctor profile not found.'},404
        if db.session.scalar(db.select(User.id).where(User.doctor_id == doctor.id)):
            return {'error':'This doctor already has an account. Use Edit account.'},409
        if department_conflict(doctor,values['department']):
            return {'error':'Resolve future confirmed bookings before changing this doctor’s department.'},409
        doctor.name=values['name']; doctor.department=values['department']
        doctor.active=values.get('active',doctor.active)
    else:
        doctor=Doctor(name=values['name'],department=values['department'],active=values.get('active',True))
        db.session.add(doctor); db.session.flush()
        db.session.add_all(WeeklyAvailability(doctor_id=doctor.id,**day) for day in default_week())
    user=User(name=doctor.name,email=values['email'],password_hash=values['password_hash'],role='doctor',
              doctor_id=doctor.id,enabled=doctor.active,demo_doctor=False)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback(); return {'error':'This email or doctor profile already has an account.'},409
    return dict(account_json(doctor,user),action_message='Doctor account created.'),201


@accounts_bp.patch('/api/admin/doctors/<int:doctor_id>')
@roles('admin')
def update_doctor(doctor_id):
    values=fields(payload())
    if not values:
        raise ValueError('Enter a profile, password, or active-status change.')
    lock_schedule()
    doctor=db.session.get(Doctor,doctor_id)
    if not doctor:
        return {'error':'Doctor profile not found.'},404
    user=db.session.scalar(db.select(User).where(User.doctor_id == doctor_id))
    if user and user.role != 'doctor':
        return {'error':'This profile is not linked to a doctor account.'},409
    if not user and ('email' in values or 'password_hash' in values):
        return {'error':'Create an account for this profile first.'},409
    if 'department' in values and department_conflict(doctor,values['department']):
        return {'error':'Resolve future confirmed bookings before changing this doctor’s department.'},409
    if 'email' in values and db.session.scalar(db.select(User.id).where(User.email == values['email'],User.id != user.id)):
        return {'error':'That email address is already registered.'},409
    for key in ('name','department','active'):
        if key in values: setattr(doctor,key,values[key])
    if user:
        user.name=doctor.name; user.enabled=doctor.active
        for key in ('email','password_hash'):
            if key in values: setattr(user,key,values[key])
        if user.email != 'doctor@mediqueue.test': user.demo_doctor=False
        user.auth_version+=1
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback(); return {'error':'That email address is already registered.'},409
    message='Doctor account updated. Existing appointments are retained.'
    if not doctor.active: message='Doctor deactivated and signed out. Existing appointments are retained for admin review.'
    return dict(account_json(doctor,user),action_message=message)
