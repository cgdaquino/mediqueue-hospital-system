from . import db
from .scheduling import end_time


class Doctor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    department = db.Column(db.String(80), nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False, default=60, server_default='60')
    active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.text('1'))
    settings_version = db.Column(db.Integer,nullable=False,default=0,server_default='0')


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='patient')
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), unique=True)
    demo_doctor = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text('0'))
    enabled = db.Column(db.Boolean,nullable=False,default=True,server_default=db.text('1'))
    auth_version = db.Column(db.Integer,nullable=False,default=0,server_default='0')


class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient = db.Column(db.String(120), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    date = db.Column(db.String(10), nullable=False)
    time = db.Column(db.String(5), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Confirmed')
    type = db.Column(db.String(20), nullable=False, default='Online')
    duration_minutes = db.Column(db.Integer, nullable=False, default=60, server_default='60')
    patient_hidden = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text('0'))
    version = db.Column(db.Integer,nullable=False,default=0,server_default='0')
    doctor = db.relationship(Doctor)
    __table_args__ = (
        db.Index('unique_occupied_slot', 'doctor_id', 'date', 'time', unique=True,
                 sqlite_where=db.text("status != 'Cancelled'")),
    )

    def as_dict(self):
        return dict(id=self.id, reference=f'MQ-{self.id:04d}', patient=self.patient,
                    doctor_id=self.doctor_id, doctor=self.doctor.name,
                    department=self.doctor.department, date=self.date, time=self.time,
                    status=self.status, type=self.type, end_time=end_time(self.time,self.duration_minutes),
                    duration_minutes=self.duration_minutes)


class BlockedDate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    date = db.Column(db.String(10), nullable=False)
    __table_args__ = (db.UniqueConstraint('doctor_id', 'date'),)


class WeeklyAvailability(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    weekday = db.Column(db.Integer, nullable=False)
    enabled = db.Column(db.Boolean, nullable=False)
    start = db.Column(db.String(5), nullable=False)
    end = db.Column(db.String(5), nullable=False)
    lunch_start = db.Column(db.String(5))
    lunch_end = db.Column(db.String(5))
    __table_args__ = (db.UniqueConstraint('doctor_id', 'weekday'),)

    def as_dict(self):
        return {key:getattr(self,key) for key in ('weekday','enabled','start','end','lunch_start','lunch_end')}


class Action(db.Model):
    token = db.Column(db.String(80),primary_key=True)
    user_id = db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
    doctor_id = db.Column(db.Integer,db.ForeignKey('doctor.id'))
    kind = db.Column(db.String(30),nullable=False)
    target_id = db.Column(db.Integer)
    before = db.Column(db.JSON)
    after = db.Column(db.JSON,nullable=False)
    expires_at = db.Column(db.Float,nullable=False)
    used = db.Column(db.Boolean,nullable=False,default=False)
