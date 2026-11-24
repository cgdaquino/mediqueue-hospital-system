from datetime import datetime, timedelta
from math import gcd

DURATION_MINUTES = 60
DURATION_OPTIONS = (15,30,45,60,90,120)


def valid_duration(value):
    if type(value) is not int or value not in DURATION_OPTIONS:
        raise ValueError('Choose an appointment duration of 15, 30, 45, 60, 90, or 120 minutes.')
    return value


def default_week():
    return [dict(weekday=day,enabled=day < 5,start='09:00',end='17:00',
                 lunch_start='12:00',lunch_end='13:00') for day in range(7)]


def time_minutes(value):
    if not isinstance(value,str) or len(value) != 5:
        raise ValueError('Use valid times in HH:MM format.')
    try:
        parsed = datetime.strptime(value,'%H:%M')
    except ValueError:
        raise ValueError('Use valid times in HH:MM format.')
    if parsed.strftime('%H:%M') != value or parsed.minute % 15:
        raise ValueError('Choose times in 15-minute increments.')
    return parsed.hour*60+parsed.minute


def fits_schedule(start, schedule, duration=DURATION_MINUTES):
    if not schedule['enabled']:
        return False
    beginning = time_minutes(start)
    ending = beginning+duration
    if beginning < time_minutes(schedule['start']) or ending > time_minutes(schedule['end']):
        return False
    if schedule['lunch_start']:
        if beginning < time_minutes(schedule['lunch_end']) and time_minutes(schedule['lunch_start']) < ending:
            return False
    return True


def schedule_slots(schedule, duration=DURATION_MINUTES):
    if not schedule['enabled']:
        return []
    result = []
    for minute in range(time_minutes(schedule['start']),time_minutes(schedule['end']),gcd(duration,30)):
        start = f'{minute//60:02d}:{minute%60:02d}'
        if fits_schedule(start,schedule,duration):
            result.append(start)
    return result


def validate_week(value, duration=DURATION_MINUTES):
    if not isinstance(value,list) or len(value) != 7:
        raise ValueError('Include exactly one schedule for each day of the week.')
    days = {}
    for row in value:
        if not isinstance(row,dict):
            raise ValueError('Each day must have valid schedule settings.')
        day = row.get('weekday')
        if type(day) is not int or day not in range(7) or day in days or type(row.get('enabled')) is not bool:
            raise ValueError('Include each weekday once with a working-day setting.')
        normalized = dict(weekday=day,enabled=row['enabled'],start=row.get('start'),end=row.get('end'),
                          lunch_start=row.get('lunch_start') or None,lunch_end=row.get('lunch_end') or None)
        start,end = time_minutes(normalized['start']),time_minutes(normalized['end'])
        if start >= end:
            raise ValueError('Working hours must end after they start; overnight shifts are not supported.')
        lunch_start,lunch_end = normalized['lunch_start'],normalized['lunch_end']
        if bool(lunch_start) != bool(lunch_end):
            raise ValueError('Set both lunch times, or turn off the lunch break.')
        if lunch_start and not start <= time_minutes(lunch_start) < time_minutes(lunch_end) <= end:
            raise ValueError('Lunch must start before it ends and fit within working hours.')
        if normalized['enabled'] and not schedule_slots(normalized,duration):
            raise ValueError('Each working day must leave room for a full consultation of the selected duration.')
        days[day] = normalized
    return [days[day] for day in range(7)]


def end_time(start, duration=DURATION_MINUTES):
    return (datetime.strptime(start, '%H:%M') + timedelta(minutes=duration)).strftime('%H:%M')


def overlaps(first, second, first_duration=DURATION_MINUTES, second_duration=DURATION_MINUTES):
    # Adjacent appointments may touch; their occupied intervals must not intersect.
    return time_minutes(first) < time_minutes(second)+second_duration and time_minutes(second) < time_minutes(first)+first_duration
