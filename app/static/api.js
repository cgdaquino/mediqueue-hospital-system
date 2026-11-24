async function api(path, options = {}) {
  const doctorContext=document.querySelector('meta[name="doctor-context"]')?.content;
  const portalRole=document.querySelector('meta[name="portal-role"]')?.content;
  const response = await fetch(path, {
    ...options,
    headers: {'Content-Type': 'application/json', 'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]').content,
      ...(doctorContext ? {'X-Doctor-Context':doctorContext} : {}),
      ...(portalRole ? {'X-Portal-Role':portalRole} : {}), ...options.headers}
  });
  if (response.status === 401) {
    window.location.assign('/login');
    throw new Error('Please sign in.');
  }
  const data = await response.json();
  if(doctorContext && path !== '/api/demo/doctor-pov' && ((data.doctor_id !== undefined && String(data.doctor_id) !== doctorContext) || data.code === 'CONTEXT_CHANGED')) {
    window.location.reload(); throw new Error('Doctor POV changed. Refreshing this view.');
  }
  if (!response.ok) {
    const error = new Error(data.error || 'The request failed. Please try again.');
    error.code = data.code; throw error;
  }
  if(data.action_message && typeof notifyAction === 'function') notifyAction(data.action_message,data.undo);
  if(data.undone && typeof window.dispatchEvent === 'function') window.dispatchEvent(new Event('mediqueue:changed'));
  return data;
}
function showMessage(text, error = false) {
  const message = document.getElementById('message');
  message.textContent = !error && typeof recentActionNotice === 'function' && recentActionNotice() ? '' : text;
  message.className = error ? 'text-red-700 mt-3' : 'text-teal-700 mt-3';
}
function reportError(error) { showMessage(error.message, true); }
function option(value, label) {
  const item = document.createElement('option');
  item.value = value;
  item.textContent = label;
  return item;
}
function clockLabel(time) {
  const [hour, minute] = time.split(':').map(Number);
  return `${hour % 12 || 12}:${String(minute).padStart(2, '0')} ${hour < 12 ? 'AM' : 'PM'}`;
}
function timeRange(start, end, duration = 60) {
  if (!end) {
    const [hour, minute] = start.split(':').map(Number);
    const total=hour*60+minute+duration;
    end = `${String(Math.floor(total/60)%24).padStart(2,'0')}:${String(total%60).padStart(2,'0')}`;
  }
  return `${clockLabel(start)} – ${clockLabel(end)}`;
}
function durationLabel(minutes) {
  return minutes === 60 ? '1 hour' : minutes === 120 ? '2 hours' : `${minutes} minutes`;
}
let hospitalNow='';
function canSetStatus(appointment,status) {
  if(status === 'Cancelled') return true;
  if(!hospitalNow) return false;
  const cutoff=`${appointment.date}T${status === 'Completed' ? appointment.end_time : appointment.time}:00`;
  return hospitalNow >= cutoff;
}
