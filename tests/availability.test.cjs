const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
class Element {
  constructor() { this.children=[]; this.events={}; this.attributes={}; this.value=''; this.checked=false; this.disabled=false; this.textContent=''; }
  appendChild(child) { this.children.push(child); }
  replaceChildren(...children) { this.children=children; }
  addEventListener(name,fn) { this.events[name]=fn; }
  setAttribute(name,value) { this.attributes[name]=value; }
}
const read = name => fs.readFileSync(path.join(__dirname,'../app/static',name),'utf8');
const settle = async () => { await new Promise(setImmediate); await new Promise(setImmediate); };

test('blocked-date error is inline, invalidates the date, and clears when available',async () => {
  const elements={}; const get = id => elements[id] ||= new Element();
  let availability={slots:[],blocked:true,reason:'This doctor has blocked this date. Please choose another date.'};
  const context=vm.createContext({Date,document:{getElementById:get,createElement:() => new Element(),
    querySelector:selector => selector.startsWith('meta') ? {content:'csrf'} : get('submit')},
    window:{location:{assign() {}},addEventListener() {}}, fetch:async url => ({ok:true,status:200,json:async () =>
      url === '/api/doctors' ? {today:'2026-11-24',doctors:[]} : url === '/api/appointments' ? {appointments:[],now:'2026-11-24T10:00:00'} : availability})});
  vm.runInContext(read('api.js'),context); vm.runInContext(read('patient.js'),context); await settle();
  get('doctor').value='1'; get('date').value='2026-11-26'; await context.refreshTimes();
  assert.match(get('dateWarning').textContent,/blocked this date/);
  assert.equal(get('dateWarning').hidden,false);
  assert.equal(get('date').attributes['aria-invalid'],'true');
  assert.equal(get('message').textContent,'');
  assert.equal(get('submit').disabled,true);
  availability={slots:['09:00','13:00'],blocked:false,reason:'',duration_minutes:60,schedule:{enabled:true,start:'09:00',end:'17:00',lunch_start:'12:00',lunch_end:'13:00'}};
  get('date').value='2026-11-27'; await context.refreshTimes();
  assert.equal(get('dateWarning').hidden,true);
  assert.equal(get('date').attributes['aria-invalid'],'false');
  assert.match(get('doctorHours').textContent,/Lunch: 12:00 PM – 1:00 PM/);
  assert.equal(get('time').children[1].textContent,'9:00 AM – 10:00 AM · 1 hour');
  assert.equal(get('submit').disabled,false);
  availability.duration_minutes=30;
  await context.refreshTimes();
  assert.equal(get('appointmentTimeLabel').textContent,'Appointment time · 30 minutes');
  assert.equal(get('time').children[1].textContent,'9:00 AM – 9:30 AM · 30 minutes');
});

test('doctor edits weekly hours and lunch controls and saves all seven days',async () => {
  const elements={}; const get=id => elements[id] ||= new Element();
  const days=Array.from({length:7},(_,weekday) => ({weekday,enabled:weekday<5,start:'09:00',end:'17:00',lunch_start:'12:00',lunch_end:'13:00'}));
  let saved;
  const context=vm.createContext({document:{getElementById:get,createElement:() => new Element()},
    window:{addEventListener() {}},
    api:async (url,options) => { if(options) { saved=JSON.parse(options.body); return saved; } return {days,duration_minutes:60}; },
    renderCalendar() {},refreshSchedule:async () => {}});
  vm.runInContext('let calendarWorkingHours=[];',context);
  vm.runInContext(read('working-hours.js'),context); await settle();
  assert.equal(get('workingHoursRows').children.length,7);
  const input = label => get('workingHoursRows').children.flatMap(row => row.children.flatMap(cell => cell.children)).find(element => element.attributes['aria-label'] === label);
  assert.equal(input('Saturday starts').disabled,true);
  input('Monday starts').value='10:00'; input('Monday finishes').value='16:00';
  get('consultationDuration').value='30';
  input('Monday lunch break').checked=false; input('Monday lunch break').events.change();
  assert.equal(input('Monday lunch starts').disabled,true);
  await get('workingHoursForm').events.submit({preventDefault() {}});
  assert.equal(saved.days.length,7);
  assert.equal(saved.duration_minutes,30);
  assert.deepEqual(saved.days[0],{weekday:0,enabled:true,start:'10:00',end:'16:00',lunch_start:null,lunch_end:null});
  assert.match(get('workingHoursMessage').textContent,/Availability saved/);
  assert.equal(get('saveWorkingHours').disabled,false);
});

test('patient removes only cancelled records from their displayed list',async () => {
  const elements={}; const get=id => elements[id] ||= new Element();
  let records=[{id:1,reference:'MQ-0001',doctor:'Doctor',date:'2030-01-02',time:'09:00',end_time:'09:30',duration_minutes:30,status:'Cancelled'},
    {id:2,reference:'MQ-0002',doctor:'Doctor',date:'2030-01-03',time:'09:00',end_time:'10:00',duration_minutes:60,status:'Confirmed'}];
  const requests=[];
  const scope=vm.createContext({Date,document:{getElementById:get,createElement:() => new Element(),
    querySelector:selector => selector.startsWith('meta') ? {content:'csrf'} : get('submit')},
    window:{location:{assign() {}},addEventListener() {}},fetch:async (url,options) => {
      requests.push({url,options});
      let data;
      if(url.endsWith('/patient-list')) { assert.equal(options.method,'DELETE'); records=records.filter(r => r.id !== 1); data={hidden:true}; }
      else if(url === '/api/doctors') data={today:'2026-11-24',doctors:[]};
      else data={appointments:records,now:'2026-11-24T10:00:00'};
      return {ok:true,status:200,json:async () => data};
    }});
  vm.runInContext(read('api.js'),scope); vm.runInContext(read('patient.js'),scope); await settle();
  let rows=get('appointments').children;
  assert.equal(rows.length,2);
  assert.equal(rows[0].children[1].textContent,'Remove from my list');
  assert.equal(rows[1].children[1].textContent,'Cancel');
  assert.match(rows[0].children[0].textContent,/30 minutes/);
  await rows[0].children[1].events.click();
  rows=get('appointments').children;
  assert.equal(rows.length,1);
  assert.match(rows[0].children[0].textContent,/MQ-0002/);
  assert.match(get('message').textContent,/hospital keeps the cancellation record/);
  assert.equal(requests.some(r => r.url === '/api/appointments/1/patient-list'),true);
});

test('admin refreshes cancellation status while the portal stays open',async () => {
  const elements={}; const get=id => elements[id] ||= new Element();
  const rows=[{id:1,reference:'MQ-0001',patient:'Patient',doctor:'Doctor',date:'2030-01-02',time:'09:00',end_time:'09:30',duration_minutes:30,status:'Confirmed',type:'Online'}];
  let refresh;
  const scope=vm.createContext({Date,document:{hidden:false,getElementById:get,createElement:() => new Element(),
    addEventListener() {},querySelector:selector => selector.startsWith('meta') ? {content:'csrf'} : get('submit')},
    window:{location:{assign() {}},addEventListener() {}},setInterval:fn => { refresh=fn; },
    fetch:async url => ({ok:true,status:200,json:async () => url === '/api/doctors' ? {today:'2026-11-24',doctors:[]} : {appointments:rows}})});
  vm.runInContext(read('api.js'),scope); vm.runInContext(read('admin.js'),scope); await settle();
  assert.equal(get('confirmed').textContent,1);
  rows[0].status='Cancelled'; await refresh();
  assert.equal(get('confirmed').textContent,0);
  assert.equal(get('appointmentRows').children[0].children[4].textContent,'Cancelled');
  assert.match(get('appointmentRows').children[0].children[3].textContent,/30 minutes/);
});

test('admin searches across names, sorts, and keeps filters during refresh',async () => {
  const elements={}; const get=id => elements[id] ||= new Element();
  const records=[
    {id:1,reference:'MQ-0001',patient:'Zoe Reyes',doctor:'Dr. Ana Cruz',date:'2030-01-03',time:'09:00',end_time:'10:00',duration_minutes:60,status:'Confirmed'},
    {id:2,reference:'MQ-0002',patient:'Ana Reyes',doctor:'Dr. Maria Santos',date:'2030-01-02',time:'09:00',end_time:'10:00',duration_minutes:60,status:'Completed'}];
  const scope=vm.createContext({Date,document:{hidden:false,getElementById:get,createElement:() => new Element(),
    addEventListener() {},querySelector:selector => selector.startsWith('meta') ? {content:'csrf'} : get('submit')},
    window:{location:{assign() {}},addEventListener() {}},setInterval() {},
    fetch:async url => ({ok:true,status:200,json:async () => url === '/api/doctors' ? {today:'2030-01-03',doctors:[]} : {appointments:records,now:'2030-01-03T10:00:00'}})});
  vm.runInContext(read('api.js'),scope); vm.runInContext(read('admin.js'),scope); await settle();
  const names=() => get('appointmentRows').children.map(row => row.children[0].textContent);
  assert.deepEqual(names(),['Ana Reyes','Zoe Reyes']);
  get('appointmentSearch').value='reyes maria'; get('appointmentSearch').events.input();
  assert.deepEqual(names(),['Ana Reyes']);
  await scope.refreshRecords(); assert.deepEqual(names(),['Ana Reyes']);
  assert.equal(get('appointmentSearch').value,'reyes maria');
  get('appointmentSearch').value=''; get('appointmentSort').value='doctor'; get('appointmentSort').events.change();
  assert.deepEqual(names(),['Zoe Reyes','Ana Reyes']);
  get('appointmentStatusFilter').value='Completed'; get('appointmentStatusFilter').events.change();
  assert.deepEqual(names(),['Ana Reyes']);
  get('clearAppointmentFilters').events.click(); assert.deepEqual(names(),['Ana Reyes','Zoe Reyes']);
});

test('five-second action notification provides undo and expires',async () => {
  const elements=[]; let interval,expiry,clock=100000,request;
  class NoticeElement extends Element {
    remove() { this.removed=true; }
  }
  const root=new NoticeElement();
  const scope=vm.createContext({Date:{now:() => clock},
    document:{body:root,createElement:() => { const node=new NoticeElement(); elements.push(node); return node; }},
    setInterval:fn => { interval=fn; return 1; },clearInterval() {},setTimeout:fn => { expiry=fn; return 2; },clearTimeout() {},
    api:async (path,options) => { request={path,options}; return {undone:true}; }});
  vm.runInContext(read('notifications.js'),scope);
  scope.notifyAction('Appointment cancelled.',{token:'abc',expires_at:105});
  const region=root.children[0], card=region.children[0],button=card.children[1];
  assert.equal(card.attributes.role,'status');
  assert.equal(button.textContent,'Undo (5s)');
  clock=103000; interval(); assert.equal(button.textContent,'Undo (2s)');
  await button.events.click();
  assert.equal(request.path,'/api/actions/abc/undo'); assert.equal(request.options.method,'POST');
  assert.equal(card.removed,true);
  scope.notifyAction('Saved',{token:'def',expires_at:108});
  const second=region.children[1]; clock=108000; interval();
  assert.equal(second.removed,true);
});
