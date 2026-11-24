const doctor = document.getElementById('doctor');
const date = document.getElementById('date');
const time = document.getElementById('time');
const submitButton = document.querySelector('#walkinForm button');
let availabilityVersion = 0;
let selectedDuration=60;
let adminRecords=[];
async function refreshTimes() {
  const version = ++availabilityVersion;
  time.replaceChildren(option('', 'Select time')); submitButton.disabled = true;
  if (!doctor.value || !date.value) return;
  try {
    const result = await api(`/api/availability?doctor_id=${encodeURIComponent(doctor.value)}&date=${encodeURIComponent(date.value)}`);
    if (version !== availabilityVersion) return;
    selectedDuration=result.duration_minutes;
    result.slots.forEach(t => time.appendChild(option(t, `${timeRange(t,null,selectedDuration)} · ${durationLabel(selectedDuration)}`)));
    submitButton.disabled = !result.slots.length;
    showMessage(result.reason || (result.slots.length ? '' : 'No appointments of this duration are available on this date.'),Boolean(result.reason));
  } catch (error) { if (version === availabilityVersion) reportError(error); }
}
doctor.addEventListener('change', refreshTimes); date.addEventListener('change', refreshTimes);
async function render() {
  const result=await api('/api/appointments'); hospitalNow=result.now || '';
  adminRecords=result.appointments; renderRecords();
}
function renderRecords() {
  const appointments=adminRecords;
  document.getElementById('total').textContent = appointments.length;
  document.getElementById('confirmed').textContent = appointments.filter(a => a.status === 'Confirmed').length;
  document.getElementById('completed').textContent = appointments.filter(a => a.status === 'Completed').length;
  document.getElementById('walkins').textContent = appointments.filter(a => a.type === 'Walk-in').length;
  const rows = document.getElementById('appointmentRows'); rows.replaceChildren();
  const query=document.getElementById('appointmentSearch').value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const statusFilter=document.getElementById('appointmentStatusFilter').value;
  const sort=document.getElementById('appointmentSort').value || 'date-asc';
  const filtered=appointments.filter(a => (!statusFilter || a.status === statusFilter) && query.every(term => `${a.patient} ${a.doctor} ${a.reference}`.toLocaleLowerCase().includes(term)));
  filtered.sort((a,b) => {
    const chronological=`${a.date}T${a.time}`.localeCompare(`${b.date}T${b.time}`) || a.id-b.id;
    return sort === 'patient' ? a.patient.localeCompare(b.patient,undefined,{sensitivity:'base'}) || chronological
      : sort === 'doctor' ? a.doctor.localeCompare(b.doctor,undefined,{sensitivity:'base'}) || chronological
      : sort === 'date-desc' ? -chronological : chronological;
  });
  document.getElementById('appointmentResults').textContent=`Showing ${filtered.length} of ${appointments.length} appointments`;
  if(!filtered.length) {
    const row=document.createElement('tr'), cell=document.createElement('td'); cell.colSpan=7; cell.className='p-5 text-slate-500';
    cell.textContent='No appointments match your search.'; row.appendChild(cell); rows.appendChild(row);
  }
  filtered.forEach(a => {
    const row = document.createElement('tr'); row.className = 'border-b';
    [a.patient, a.doctor, a.date, `${timeRange(a.time, a.end_time)} · ${durationLabel(a.duration_minutes)}`, a.status, a.type].forEach(value => {
      const cell = document.createElement('td'); cell.className = 'p-3'; cell.textContent = value; row.appendChild(cell);
    });
    const actions = document.createElement('td'); actions.className = 'p-3';
    if (a.status === 'Confirmed') {
      ['Completed','No-show','Cancelled'].forEach(status => {
      const button = document.createElement('button'); button.textContent = status === 'Cancelled' ? 'Cancel' : status; button.className = 'admin-status-action';
      button.disabled=!canSetStatus(a,status);
      if(button.disabled) button.title=status === 'Completed' ? 'Available after the appointment ends' : 'Available after the appointment starts';
      button.addEventListener('click', async () => {
        button.disabled = true;
        try { await api(`/api/appointments/${a.id}`, {method:'PATCH', body:JSON.stringify({status})}); await render(); await refreshTimes(); showMessage(`${a.reference} marked ${status.toLowerCase()}.`); }
        catch (error) { reportError(error); button.disabled = false; }
      }); actions.appendChild(button);
      });
    }
    row.appendChild(actions); rows.appendChild(row);
  });
}
document.getElementById('walkinForm').addEventListener('submit', async e => {
  e.preventDefault();
  const patient = document.getElementById('patient').value.trim();
  if (!patient) { showMessage('Enter a patient name.', true); return; }
  submitButton.disabled = true;
  try {
    await api('/api/appointments', {method:'POST', body:JSON.stringify({patient, doctor_id:doctor.value, date:date.value, time:time.value,duration_minutes:selectedDuration})});
    document.getElementById('patient').value = '';
    await render(); await refreshTimes(); showMessage('Walk-in registered successfully.');
  } catch (error) { await refreshTimes(); reportError(error); }
});
document.getElementById('exportButton').addEventListener('click', () => { window.location.assign('/api/reports/appointments.csv'); });
(async () => {
  submitButton.disabled = true;
  const result = await api('/api/doctors'); date.min = result.today; date.value = result.today;
  doctor.replaceChildren(option('', 'Select doctor'));
  result.doctors.forEach(d => doctor.appendChild(option(d.id, d.name)));
  await render();
})().catch(reportError);
let refreshingRecords=false;
async function refreshRecords() {
  if(refreshingRecords || document.hidden) return;
  refreshingRecords=true;
  try { await render(); } catch(error) { reportError(error); }
  finally { refreshingRecords=false; }
}
setInterval(refreshRecords,10000);
window.addEventListener('focus',refreshRecords);
document.addEventListener('visibilitychange',refreshRecords);
window.addEventListener('mediqueue:changed',() => { Promise.all([render(),refreshTimes()]).catch(reportError); });
document.getElementById('appointmentSearch').addEventListener('input',renderRecords);
document.getElementById('appointmentSort').addEventListener('change',renderRecords);
document.getElementById('appointmentStatusFilter').addEventListener('change',renderRecords);
document.getElementById('clearAppointmentFilters').addEventListener('click',() => {
  document.getElementById('appointmentSearch').value=''; document.getElementById('appointmentStatusFilter').value='';
  document.getElementById('appointmentSort').value='date-asc'; renderRecords();
});
