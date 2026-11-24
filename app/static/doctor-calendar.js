let calendarView = 'week';
let calendarToday = '';
let calendarBlockedDates = [];
let calendarWorkingHours = [];
let refreshingCalendar = false;
const calendarDateInput = document.getElementById('selectedDate');
const appointmentDialog = document.getElementById('appointmentDialog');
const MINUTE_HEIGHT = 1.25;
const FIRST_HOUR = 8;
const LAST_HOUR = 18;

// Calendar dates stay in hospital time; never parse YYYY-MM-DD as UTC.
function calendarDate(value) { return new Date(`${value}T12:00:00`); }
function dateKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}
function addDays(value, count) {
  const date = calendarDate(value); date.setDate(date.getDate() + count); return dateKey(date);
}
function weekStart(value) {
  const day = calendarDate(value).getDay(); return addDays(value, -(day + 6) % 7);
}
function minutes(value) { const [hour, minute] = value.split(':').map(Number); return hour * 60 + minute; }
function element(tag, className, text) {
  const node = document.createElement(tag); node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function appointmentClass(status) { return status === 'Cancelled' ? 'cancelled' : status === 'Completed' ? 'completed' : status === 'No-show' ? 'no-show' : 'confirmed'; }

function openAppointment(appointment) {
  calendarDateInput.value = appointment.date; renderQueue(); renderCalendar();
  document.getElementById('appointmentTitle').textContent = appointment.patient;
  document.getElementById('appointmentDetails').textContent = `${calendarDate(appointment.date).toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric'})}\n${timeRange(appointment.time,appointment.end_time)} · ${durationLabel(appointment.duration_minutes)}\n${appointment.reference} · ${appointment.type}`;
  document.getElementById('appointmentStatus').textContent = appointment.status;
  const actions = document.getElementById('appointmentActions'); actions.replaceChildren();
  if (appointment.status === 'Confirmed') {
    ['Completed','No-show','Cancelled'].forEach(status => {
      const button = element('button','calendar-control',`Mark ${status.toLowerCase()}`);
      button.disabled=!canSetStatus(appointment,status);
      if(button.disabled) button.title=status === 'Completed' ? 'Available after the appointment ends' : 'Available after the appointment starts';
      button.addEventListener('click',async () => {
        button.disabled = true;
        try {
          await api(`/api/appointments/${appointment.id}`,{method:'PATCH',body:JSON.stringify({status})});
          appointmentDialog.close(); await loadQueue(); showMessage(`${appointment.reference} marked ${status.toLowerCase()}.`);
        } catch(error) { appointmentDialog.close(); reportError(error); }
      }); actions.appendChild(button);
    });
  }
  appointmentDialog.showModal();
}
document.getElementById('closeAppointment').addEventListener('click',() => appointmentDialog.close());

// Place legacy overlaps side by side rather than hiding one behind another.
function eventLanes(events) {
  const groups = [];
  events.forEach(event => {
    const last = groups[groups.length-1];
    const start = minutes(event.time), end = minutes(event.end_time);
    if (!last || start >= last.end) groups.push({end,events:[event]});
    else { last.events.push(event); last.end = Math.max(last.end,end); }
  });
  return groups.flatMap(group => {
    const ends = [];
    const placed = group.events.map(event => {
      let lane = ends.findIndex(end => end <= minutes(event.time));
      if (lane < 0) lane = ends.length;
      ends[lane] = minutes(event.end_time);
      return {event,lane};
    });
    return placed.map(item => ({...item,lanes:ends.length}));
  });
}

function renderCalendar() {
  if (!calendarDateInput.value) return;
  const start = calendarView === 'week' ? weekStart(calendarDateInput.value) : calendarDateInput.value;
  const dates = Array.from({length:calendarView === 'week' ? 7 : 1},(_,index) => addDays(start,index));
  const dayHours = day => calendarWorkingHours.find(row => row.weekday === (calendarDate(day).getDay()+6)%7);
  const working = calendarWorkingHours.filter(row => row.enabled);
  const firstHour = Math.min(FIRST_HOUR,...working.map(row => Math.floor(minutes(row.start)/60)));
  const lastHour = Math.max(LAST_HOUR,...working.map(row => Math.ceil(minutes(row.end)/60)));
  const grid = document.getElementById('calendarGrid'); grid.replaceChildren();
  grid.style.gridTemplateColumns = `64px repeat(${dates.length}, minmax(120px, 1fr))`;
  grid.classList.toggle('day-view',calendarView === 'day');
  document.getElementById('previousPeriod').setAttribute('aria-label',`Previous ${calendarView}`);
  document.getElementById('nextPeriod').setAttribute('aria-label',`Next ${calendarView}`);
  document.getElementById('weekView').setAttribute('aria-pressed',String(calendarView === 'week'));
  document.getElementById('dayView').setAttribute('aria-pressed',String(calendarView === 'day'));
  const shortDate = value => calendarDate(value).toLocaleDateString('en-US',{month:'short',day:'numeric'});
  document.getElementById('calendarTitle').textContent = calendarView === 'week'
    ? `${shortDate(dates[0])} – ${shortDate(dates[6])}, ${calendarDate(dates[6]).getFullYear()}`
    : calendarDate(start).toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric'});
  grid.appendChild(element('div','calendar-corner','PHT'));
  dates.forEach(day => {
    const header = element('button',`calendar-day-header${day === calendarToday ? ' is-today' : ''}${day === calendarDateInput.value ? ' is-selected' : ''}`);
    header.setAttribute('aria-label',`Show queue for ${day}`);
    header.setAttribute('aria-pressed',String(day === calendarDateInput.value));
    header.appendChild(element('span','',calendarDate(day).toLocaleDateString('en-US',{weekday:'short'})));
    header.appendChild(element('strong','',String(calendarDate(day).getDate())));
    header.addEventListener('click',() => { calendarDateInput.value = day; renderQueue(); renderCalendar(); });
    grid.appendChild(header);
  });
  grid.appendChild(element('div','calendar-allday-label','All day'));
  dates.forEach(day => {
    const cell = element('div','calendar-allday');
    if (calendarBlockedDates.includes(day)) cell.appendChild(element('span','blocked-label','Unavailable'));
    else if (dayHours(day) && !dayHours(day).enabled) cell.appendChild(element('span','blocked-label','Not working'));
    grid.appendChild(cell);
  });
  const gutter = element('div','calendar-time-gutter');
  gutter.style.height = `${(lastHour-firstHour)*60*MINUTE_HEIGHT}px`;
  for(let hour=firstHour;hour<lastHour;hour++) {
    const label = element('span','calendar-hour',clockLabel(`${hour}:00`));
    label.style.top = `${(hour-firstHour)*60*MINUTE_HEIGHT}px`; gutter.appendChild(label);
  }
  grid.appendChild(gutter);
  let count = 0, cancelledCount=0;
  dates.forEach(day => {
    const hours = dayHours(day);
    const closed = calendarBlockedDates.includes(day) || (hours && !hours.enabled);
    const column = element('div',`calendar-day-column${day === calendarToday ? ' is-today' : ''}${closed ? ' is-blocked' : ''}`);
    column.style.height = gutter.style.height;
    if(hours && hours.enabled && !closed) {
      const shade = (start,end,label,className) => {
        if(end <= start) return;
        const block=element('div',className,label);
        block.style.top=`${(start-firstHour*60)*MINUTE_HEIGHT}px`;
        block.style.height=`${(end-start)*MINUTE_HEIGHT}px`; column.appendChild(block);
      };
      shade(firstHour*60,minutes(hours.start),'','calendar-closed-period');
      shade(minutes(hours.end),lastHour*60,'','calendar-closed-period');
      if(hours.lunch_start) shade(minutes(hours.lunch_start),minutes(hours.lunch_end),`Lunch · ${timeRange(hours.lunch_start,hours.lunch_end)}`,'calendar-lunch-period');
    }
    const daily = appointments.filter(a => a.date === day).sort((a,b) => a.time.localeCompare(b.time) || a.id-b.id);
    count += daily.length;
    cancelledCount+=daily.filter(a => a.status === 'Cancelled').length;
    eventLanes(daily).forEach(({event,lane,lanes}) => {
      const card = element('button',`calendar-event ${appointmentClass(event.status)}`);
      if(event.duration_minutes <= 30) card.className+=' compact';
      if(event.duration_minutes <= 15) card.className+=' tiny';
      card.style.top = `${(minutes(event.time)-firstHour*60)*MINUTE_HEIGHT}px`;
      card.style.height = `${event.duration_minutes*MINUTE_HEIGHT-4}px`;
      card.style.left = `calc(${lane/lanes*100}% + 3px)`;
      card.style.width = `calc(${100/lanes}% - 6px)`;
      card.setAttribute('aria-label',`${event.patient}, ${event.date}, ${timeRange(event.time,event.end_time)}, ${event.status}`);
      card.appendChild(element('strong','',event.patient));
      card.appendChild(element('span','',timeRange(event.time,event.end_time)));
      card.appendChild(element('small','',event.status));
      card.addEventListener('click',() => openAppointment(event));
      column.appendChild(card);
    });
    grid.appendChild(column);
  });
  document.getElementById('calendarSummary').textContent = `${count} appointment${count === 1 ? '' : 's'} this ${calendarView}${cancelledCount ? ` · ${cancelledCount} cancelled` : ''}`;
}

async function refreshSchedule() {
  if (refreshingCalendar || !calendarDateInput.value) return;
  refreshingCalendar = true;
  document.getElementById('refreshCalendar').disabled = true;
  try {
    const results=await Promise.all([loadQueue(),loadBlocked(),api('/api/working-hours')]);
    calendarWorkingHours=results[2].days || []; renderCalendar();
    document.getElementById('calendarDurationLabel').textContent=`New consultations: ${durationLabel(results[2].duration_minutes)} · Philippine Time (PHT, UTC+8)`;
    document.getElementById('calendarSync').textContent = 'Up to date · checks every 10 seconds';
  } catch(error) { document.getElementById('calendarSync').textContent = 'Could not update · try Refresh'; }
  finally { refreshingCalendar = false; document.getElementById('refreshCalendar').disabled = false; }
}
document.getElementById('previousPeriod').addEventListener('click',() => { calendarDateInput.value = addDays(calendarDateInput.value,calendarView === 'week' ? -7 : -1); renderQueue(); renderCalendar(); refreshSchedule(); });
document.getElementById('nextPeriod').addEventListener('click',() => { calendarDateInput.value = addDays(calendarDateInput.value,calendarView === 'week' ? 7 : 1); renderQueue(); renderCalendar(); refreshSchedule(); });
document.getElementById('todayButton').addEventListener('click',() => { calendarDateInput.value = calendarToday; renderQueue(); renderCalendar(); refreshSchedule(); });
['week','day'].forEach(view => document.getElementById(`${view}View`).addEventListener('click',() => { calendarView = view; renderCalendar(); }));
document.getElementById('refreshCalendar').addEventListener('click',refreshSchedule);
window.addEventListener('focus',refreshSchedule);
document.addEventListener('visibilitychange',() => { if (!document.hidden) refreshSchedule(); });
setInterval(() => { if (!document.hidden) refreshSchedule(); },10000);
