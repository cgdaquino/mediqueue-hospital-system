const selectedDate = document.getElementById('selectedDate');
let appointments = [];
let queueVersion = 0;
function renderQueue() {
  document.getElementById('queueDateLabel').textContent = selectedDate.value
    ? calendarDate(selectedDate.value).toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric'}) : '';
  const daily = appointments.filter(a => a.date === selectedDate.value);
  const active=daily.filter(a => a.status !== 'Cancelled');
  document.getElementById('total').textContent = active.length;
  document.getElementById('completed').textContent = daily.filter(a => a.status === 'Completed').length;
  document.getElementById('waiting').textContent = daily.filter(a => a.status === 'Confirmed').length;
  const container = document.getElementById('queue'); container.replaceChildren();
  if (!daily.length) container.textContent = 'No appointments scheduled.';
  daily.forEach((a, index) => {
    const row = document.createElement('div');
    row.className = 'border rounded-lg p-4 flex flex-wrap items-center justify-between gap-3';
    const info = document.createElement('p');
    info.textContent = `${a.status === 'Cancelled' ? 'Cancelled appointment' : `Queue ${active.findIndex(item => item.id === a.id)+1}`} | ${timeRange(a.time,a.end_time)} | ${a.patient} | ${a.status}`;
    if(a.status === 'Cancelled') row.className+=' cancelled-record';
    row.appendChild(info);
    if (a.status === 'Confirmed') {
      ['Completed', 'No-show','Cancelled'].forEach(status => {
        const button = document.createElement('button'); button.textContent = status;
        button.className = 'text-teal-700 font-medium';
        button.disabled=!canSetStatus(a,status);
        if(button.disabled) button.title=status === 'Completed' ? 'Available after the appointment ends' : 'Available after the appointment starts';
        button.addEventListener('click', async () => {
          button.disabled = true;
          try {
            await api(`/api/appointments/${a.id}`, {method:'PATCH', body:JSON.stringify({status})});
            await loadQueue(); showMessage(`${a.reference} marked ${status.toLowerCase()}.`);
          } catch (error) { reportError(error); button.disabled = false; }
        });
        row.appendChild(button);
      });
    }
    container.appendChild(row);
  });
}
async function loadQueue() {
  const version = ++queueVersion;
  const result = await api('/api/appointments');
  if (version !== queueVersion) return;
  hospitalNow=result.now || ''; appointments = result.appointments; renderQueue(); renderCalendar();
}
async function loadBlocked() {
  const result = await api('/api/blocked-dates');
  calendarBlockedDates = result.dates; renderCalendar();
  const list = document.getElementById('blockedList'); list.replaceChildren();
  result.dates.forEach(date => {
    const item = document.createElement('li');
    const label = document.createElement('span'); label.textContent = `Unavailable: ${date} `; item.appendChild(label);
    const button = document.createElement('button'); button.textContent = 'Unblock'; button.className = 'text-teal-700 underline';
    button.addEventListener('click', async () => {
      button.disabled = true;
      try { await api('/api/blocked-dates', {method:'DELETE', body:JSON.stringify({date})}); await loadBlocked(); showMessage('Date unblocked.'); }
      catch (error) { reportError(error); button.disabled = false; }
    });
    item.appendChild(button); list.appendChild(item);
  });
}
document.getElementById('blockButton').addEventListener('click', async e => {
  e.target.disabled = true;
  try {
    await api('/api/blocked-dates', {method:'POST', body:JSON.stringify({date:document.getElementById('blockedDate').value})});
    await loadBlocked(); showMessage('Date blocked.');
  } catch (error) { reportError(error); }
  finally { e.target.disabled = false; }
});
selectedDate.addEventListener('change', () => loadQueue().catch(reportError));
(async () => {
  const result = await api('/api/doctors'); if(!selectedDate.value) selectedDate.value = result.today;
  calendarToday = result.today;
  document.getElementById('blockedDate').min = result.today;
  await refreshSchedule();
})().catch(reportError);
window.addEventListener('mediqueue:changed',refreshSchedule);
document.getElementById('calendarTab').addEventListener('click',() => setScheduleView('calendar'));
document.getElementById('queueTab').addEventListener('click',() => setScheduleView('queue'));
function setScheduleView(view) {
  document.getElementById('calendarPanel').hidden=view !== 'calendar';
  document.getElementById('queuePanel').hidden=view !== 'queue';
  document.getElementById('calendarTab').setAttribute('aria-selected',String(view === 'calendar'));
  document.getElementById('queueTab').setAttribute('aria-selected',String(view === 'queue'));
}
const povSelect=document.getElementById('doctorPov');
if(povSelect) povSelect.addEventListener('change',async () => {
  povSelect.disabled=true;
  try { await api('/api/demo/doctor-pov',{method:'POST',body:JSON.stringify({doctor_id:povSelect.value})}); window.location.reload(); }
  catch(error) { reportError(error); povSelect.disabled=false; }
});
