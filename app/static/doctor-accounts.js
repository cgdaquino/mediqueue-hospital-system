let doctorAccounts=[],editingDoctor=null;
const accountForm=document.getElementById('doctorAccountForm');
const accountProfile=document.getElementById('accountProfile');
function accountMessage(message,error=false) {
  const node=document.getElementById('doctorAccountMessage'); node.textContent=message;
  node.className=error ? 'hours-error' : 'doctor-accounts-note';
}
function fillDoctorAccount(doctor,editing) {
  editingDoctor=editing ? doctor.doctor_id : null;
  accountProfile.value=editing ? '' : String(doctor.doctor_id);
  document.getElementById('doctorProfileLabel').hidden=editing;
  document.getElementById('accountDoctorName').value=doctor.name;
  document.getElementById('accountDepartment').value=doctor.department;
  document.getElementById('accountEmail').value=doctor.email || '';
  document.getElementById('accountPassword').value='';
  document.getElementById('accountPassword').required=!editing;
  document.getElementById('accountPasswordLabel').textContent=editing ? 'New password (optional)' : 'Initial password';
  document.getElementById('accountPasswordHelp').textContent=editing ? 'Leave blank to keep the current password.' : '8–128 characters. Share it with the doctor privately.';
  document.getElementById('accountActive').checked=doctor.active;
  document.getElementById('saveDoctorAccount').textContent=editing ? 'Save doctor account' : 'Create doctor account';
  document.getElementById('cancelDoctorEdit').hidden=!editing;
  accountMessage(editing ? `Editing ${doctor.name}. Changes sign this doctor out; appointment history is retained.` : `Creating a login for ${doctor.name}'s existing profile.`);
  document.getElementById('doctorAccountsPanel').open=true;
}
function resetDoctorAccountForm() {
  editingDoctor=null; accountForm.reset();
  document.getElementById('doctorProfileLabel').hidden=false;
  document.getElementById('accountPassword').required=true;
  document.getElementById('accountPasswordLabel').textContent='Initial password';
  document.getElementById('accountPasswordHelp').textContent='8–128 characters. Share it with the doctor privately.';
  document.getElementById('saveDoctorAccount').textContent='Create doctor account';
  document.getElementById('cancelDoctorEdit').hidden=true;
}
async function reloadBookingDoctors() {
  const previous=doctor.value;
  const data=await api('/api/doctors'); doctor.replaceChildren(option('','Select doctor'));
  data.doctors.forEach(row => doctor.appendChild(option(row.id,row.name)));
  if(data.doctors.some(row => String(row.id) === previous)) doctor.value=previous;
  await refreshTimes();
}
async function loadDoctorAccounts() {
  const data=await api('/api/admin/doctors'); doctorAccounts=data.doctors;
  accountProfile.replaceChildren(option('','Add a new doctor profile'));
  doctorAccounts.filter(row => !row.has_account).forEach(row => accountProfile.appendChild(option(row.doctor_id,`${row.name} · ${row.department}${row.active ? '' : ' (inactive)'}`)));
  const body=document.getElementById('doctorAccountRows'); body.replaceChildren();
  doctorAccounts.forEach(row => {
    const tr=document.createElement('tr');
    [ `${row.name} · ${row.department}`,row.email || 'No login yet',row.active ? (row.has_account ? 'Active' : 'Profile only') : 'Inactive',String(row.future_confirmed)].forEach(text => {
      const cell=document.createElement('td'); cell.textContent=text; tr.appendChild(cell);
    });
    const actions=document.createElement('td');
    const edit=document.createElement('button'); edit.type='button'; edit.className='admin-status-action';
    edit.textContent=row.has_account ? 'Edit account' : 'Create account';
    edit.setAttribute('aria-label',`${row.has_account ? 'Edit account for' : 'Create account for'} ${row.name}`);
    edit.addEventListener('click',() => { fillDoctorAccount(row,row.has_account); accountForm.scrollIntoView({behavior:'auto',block:'center'}); });
    actions.appendChild(edit);
    const toggle=document.createElement('button'); toggle.type='button'; toggle.className='admin-status-action';
    toggle.textContent=row.active ? 'Deactivate' : 'Activate'; toggle.setAttribute('aria-label',`${toggle.textContent} ${row.name}`);
    toggle.addEventListener('click',async () => {
      toggle.disabled=true;
      try {
        await api(`/api/admin/doctors/${row.doctor_id}`,{method:'PATCH',body:JSON.stringify({active:!row.active})});
        if(editingDoctor === row.doctor_id) resetDoctorAccountForm();
        await loadDoctorAccounts(); await reloadBookingDoctors();
        accountMessage(row.active ? `${row.name} deactivated. ${row.future_confirmed} future confirmed appointment(s) remain for review.` : `${row.name} activated.`);
      } catch(error) { accountMessage(error.message,true); toggle.disabled=false; }
    });
    actions.appendChild(toggle); tr.appendChild(actions); body.appendChild(tr);
  });
}
accountProfile.addEventListener('change',() => {
  if(!accountProfile.value) { resetDoctorAccountForm(); accountMessage('Adding a new doctor profile and login.'); return; }
  const row=doctorAccounts.find(row => String(row.doctor_id) === accountProfile.value);
  if(row) fillDoctorAccount(row,false);
});
document.getElementById('cancelDoctorEdit').addEventListener('click',() => { resetDoctorAccountForm(); accountMessage('Edit cancelled.'); });
accountForm.addEventListener('submit',async event => {
  event.preventDefault(); const button=document.getElementById('saveDoctorAccount'); button.disabled=true;
  const data={name:document.getElementById('accountDoctorName').value,email:document.getElementById('accountEmail').value,
    department:document.getElementById('accountDepartment').value,active:document.getElementById('accountActive').checked};
  const password=document.getElementById('accountPassword').value;
  if(password) data.password=password;
  if(!editingDoctor && accountProfile.value) data.doctor_id=Number(accountProfile.value);
  try {
    await api(editingDoctor ? `/api/admin/doctors/${editingDoctor}` : '/api/admin/doctors',
      {method:editingDoctor ? 'PATCH' : 'POST',body:JSON.stringify(data)});
    resetDoctorAccountForm(); await loadDoctorAccounts(); await reloadBookingDoctors(); await render();
    accountMessage('Saved. Public registration remains patient-only.');
  } catch(error) { accountMessage(error.message,true); }
  finally { button.disabled=false; }
});
loadDoctorAccounts().catch(error => accountMessage(error.message,true));
