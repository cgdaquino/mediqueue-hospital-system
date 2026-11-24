const weekdayNames = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
let workingHourInputs = [];
function hoursMessage(message,error=false) {
  const target = document.getElementById('workingHoursMessage'); target.textContent = message;
  target.className = error ? 'hours-error' : 'hours-success';
}
function renderWorkingHours(days) {
  const body = document.getElementById('workingHoursRows'); body.replaceChildren(); workingHourInputs=[];
  days.forEach(day => {
    const row = document.createElement('tr');
    const label = document.createElement('th'); label.scope='row'; label.textContent=weekdayNames[day.weekday]; row.appendChild(label);
    const inputs = {};
    const fields = [['enabled','checkbox',day.enabled,'working'],['start','time',day.start,'starts'],['end','time',day.end,'finishes'],
      ['lunch','checkbox',Boolean(day.lunch_start),'lunch break'],['lunch_start','time',day.lunch_start || '12:00','lunch starts'],['lunch_end','time',day.lunch_end || '13:00','lunch ends']];
    fields.forEach(([key,type,value,name]) => {
      const cell=document.createElement('td'), input=document.createElement('input');
      input.type=type; input.setAttribute('aria-label',`${weekdayNames[day.weekday]} ${name}`);
      if(type === 'checkbox') input.checked=value;
      else { input.value=value; input.step='900'; input.required=true; }
      inputs[key]=input; cell.appendChild(input); row.appendChild(cell);
    });
    function updateEnabled() {
      ['start','end','lunch'].forEach(key => { inputs[key].disabled = !inputs.enabled.checked; });
      ['lunch_start','lunch_end'].forEach(key => { inputs[key].disabled = !inputs.enabled.checked || !inputs.lunch.checked; });
    }
    inputs.enabled.addEventListener('change',updateEnabled); inputs.lunch.addEventListener('change',updateEnabled);
    updateEnabled(); workingHourInputs.push({weekday:day.weekday,inputs}); body.appendChild(row);
  });
}
document.getElementById('workingHoursForm').addEventListener('submit',async event => {
  event.preventDefault(); const button=document.getElementById('saveWorkingHours'); button.disabled=true;
  const days=workingHourInputs.map(({weekday,inputs:i}) => ({weekday,enabled:i.enabled.checked,
    start:i.start.value || '09:00',end:i.end.value || '17:00',
    lunch_start:i.lunch.checked ? i.lunch_start.value : null,lunch_end:i.lunch.checked ? i.lunch_end.value : null}));
  try {
    const result=await api('/api/working-hours',{method:'PUT',body:JSON.stringify({days,duration_minutes:Number(document.getElementById('consultationDuration').value)})});
    calendarWorkingHours=result.days; renderWorkingHours(result.days); await refreshSchedule();
    hoursMessage('Availability saved. Patients and walk-ins will use these hours.');
  } catch(error) { hoursMessage(error.message,true); }
  finally { button.disabled=false; }
});
async function loadWorkingHours() {
  const result=await api('/api/working-hours'); calendarWorkingHours=result.days;
  document.getElementById('consultationDuration').value=String(result.duration_minutes);
  document.getElementById('consultationDuration').disabled=false;
  renderWorkingHours(result.days); renderCalendar(); hoursMessage('Your saved weekly hours');
  document.getElementById('saveWorkingHours').disabled=false;
}
loadWorkingHours().catch(error => hoursMessage(error.message,true));
window.addEventListener('mediqueue:changed',() => loadWorkingHours().catch(error => hoursMessage(error.message,true)));
