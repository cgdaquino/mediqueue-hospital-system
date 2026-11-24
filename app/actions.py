import secrets
import time

from . import db
from .models import Action, WeeklyAvailability


def appointment_state(appointment):
    return {key:getattr(appointment,key) for key in ('status','patient_hidden','doctor_id','date','time','duration_minutes','patient_id','version')}


def settings_state(doctor):
    return {'duration_minutes':doctor.duration_minutes,'version':doctor.settings_version,
            'days':[row.as_dict() for row in db.session.scalars(db.select(WeeklyAvailability).filter_by(doctor_id=doctor.id).order_by(WeeklyAvailability.weekday))]}


def remember(user_id,kind,target_id,before,after,doctor_id=None):
    action=Action(token=secrets.token_urlsafe(24),user_id=user_id,doctor_id=doctor_id,kind=kind,
                  target_id=target_id,before=before,after=after,expires_at=time.time()+5)
    db.session.add(action)
    return {'token':action.token,'expires_at':action.expires_at,'seconds':5}
