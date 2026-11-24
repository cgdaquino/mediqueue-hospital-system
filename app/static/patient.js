let doctors = [], bookings = [], availabilityVersion = 0;
let selectedDuration=60;
const department = document.getElementById('department');
const doctor = document.getElementById('doctor');
const date = document.getElementById('date');
const time = document.getElementById('time');
const submitButton = document.querySelector('#bookingForm button');
function dateWarning(text) {
  const warning = document.getElementById('dateWarning');
  warning.textContent = text; warning.hidden = !text;
  date.setAttribute('aria-invalid',text ? 'true' : 'false');
}
async function refreshTimes() {
  const version = ++availabilityVersion;
  submitButton.disabled = true;
  time.replaceChildren(option('', 'Select time'));
  dateWarning(''); document.getElementById('doctorHours').textContent = ''; showMessage('');
  document.getElementById('appointmentTimeLabel').textContent='Appointment time';
  document.getElementById('appointmentDurationNote').textContent='Consultation length is set by your doctor. Choose a doctor and date to see available time ranges.';
  if (!doctor.value || !date.value) return;
  try {
    const result = await api(`/api/availability?doctor_id=${encodeURIComponent(doctor.value)}&date=${encodeURIComponent(date.value)}`);
    if (version !== availabilityVersion) return;
    selectedDuration=result.duration_minutes;
    document.getElementById('appointmentTimeLabel').textContent=`Appointment time · ${durationLabel(selectedDuration)}`;
    document.getElementById('appointmentDurationNote').textContent=`This doctor's consultations last ${durationLabel(selectedDuration)}. Times use Philippine Time (PHT, UTC+8).`;
    result.slots.forEach(slot => time.appendChild(option(slot, `${timeRange(slot,null,selectedDuration)} · ${durationLabel(selectedDuration)}`)));
    dateWarning(result.reason || '');
    const hours = result.schedule;
    if (hours && hours.enabled && !result.blocked) {
      document.getElementById('doctorHours').textContent = `Clinic hours: ${timeRange(hours.start,hours.end)}${hours.lunch_start ? ` · Lunch: ${timeRange(hours.lunch_start,hours.lunch_end)}` : ''}`;
    }
    showMessage(result.reason || result.slots.length ? '' : 'No appointments of this duration are available on this date. Please choose another date.');
    submitButton.disabled = !result.slots.length;
  } catch (error) { if (version === availabilityVersion) reportError(error); }
}
department.addEventListener('change', () => {
  doctor.replaceChildren(option('', 'Select doctor'));
  doctors.filter(d => d.department === department.value).forEach(d => doctor.appendChild(option(d.id, d.name)));
  refreshTimes();
});
doctor.addEventListener('change', refreshTimes);
date.addEventListener('change', refreshTimes);
async function loadBookings() {
  const result = await api('/api/appointments');
  bookings = result.appointments;
  const future = b => `${b.date}T${b.time}:00` > result.now;
  document.getElementById('upcoming').textContent = bookings.filter(b => b.status === 'Confirmed' && future(b)).length;
  document.getElementById('completed').textContent = bookings.filter(b => b.status === 'Completed').length;
  const container = document.getElementById('appointments');
  container.replaceChildren();
  if (!bookings.length) container.textContent = 'No appointments yet.';
  bookings.forEach(b => {
    const row = document.createElement('div');
    row.className = 'border rounded-lg p-4 flex flex-wrap justify-between gap-3';
    const details = document.createElement('p');
    details.textContent = `${b.reference} | ${b.doctor} | ${b.date} | ${timeRange(b.time, b.end_time)} · ${durationLabel(b.duration_minutes)} | ${b.status}`;
    row.appendChild(details);
    if (b.status === 'Confirmed' && future(b)) {
      const button = document.createElement('button');
      button.textContent = 'Cancel';
      button.className = 'text-red-600 font-medium';
      button.addEventListener('click', async () => {
        button.disabled = true;
        try {
          await api(`/api/appointments/${b.id}`, {method:'PATCH', body:JSON.stringify({status:'Cancelled'})});
          await loadBookings(); await refreshTimes(); showMessage(`${b.reference} cancelled.`);
        } catch (error) { reportError(error); button.disabled = false; }
      });
      row.appendChild(button);
    }
    if(b.status === 'Cancelled') {
      const remove=document.createElement('button');
      remove.textContent='Remove from my list'; remove.className='text-slate-600 underline';
      remove.addEventListener('click',async () => {
        remove.disabled=true;
        try {
          await api(`/api/appointments/${b.id}/patient-list`,{method:'DELETE'});
          await loadBookings(); showMessage(`${b.reference} removed from your list. The hospital keeps the cancellation record.`);
        } catch(error) { reportError(error); remove.disabled=false; }
      });
      row.appendChild(remove);
    }
    container.appendChild(row);
  });
}
document.getElementById('bookingForm').addEventListener('submit', async e => {
  e.preventDefault(); submitButton.disabled = true;
  try {
    const result = await api('/api/appointments', {method:'POST', body:JSON.stringify({doctor_id:doctor.value, date:date.value, time:time.value,duration_minutes:selectedDuration})});
    await loadBookings(); await refreshTimes(); showMessage(`Appointment ${result.reference} confirmed: ${timeRange(result.time, result.end_time)} (${durationLabel(result.duration_minutes)}).`);
  } catch (error) {
    await refreshTimes();
    if (!document.getElementById('dateWarning').textContent) reportError(error);
  }
});
(async () => {
  submitButton.disabled = true;
  const result = await api('/api/doctors');
  doctors = result.doctors; date.min = result.today;
  department.replaceChildren(option('', 'Select department'));
  [...new Set(doctors.map(d => d.department))].forEach(d => department.appendChild(option(d, d)));
  await loadBookings();
})().catch(reportError);
window.addEventListener('mediqueue:changed',() => { Promise.all([loadBookings(),refreshTimes()]).catch(reportError); });
