const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const fakeElement = {addEventListener() {}};
const context = vm.createContext({Date, document:{getElementById:() => fakeElement,addEventListener() {}},window:{addEventListener() {}},setInterval() {}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../app/static/doctor-calendar.js'),'utf8'),context);
test('calendar week begins Monday across month and year boundaries',() => {
  for (const [input,expected] of [['2026-11-24','2026-11-23'],['2027-01-01','2026-12-28'],['2026-11-29','2026-11-23'],['2026-11-23','2026-11-23']]) {
    assert.equal(context.weekStart(input),expected);
  }
  assert.equal(context.addDays('2026-12-31',1),'2027-01-01');
  assert.equal(context.addDays('2028-02-28',1),'2028-02-29');
});
test('overlapping legacy bookings remain visible in separate lanes',() => {
  const result = context.eventLanes([
    {id:1,time:'09:00',end_time:'10:00'},
    {id:2,time:'09:30',end_time:'10:30'},
    {id:3,time:'10:00',end_time:'11:00'},
    {id:4,time:'11:00',end_time:'12:00'}
  ]);
  assert.deepEqual(Array.from(result,r => [r.event.id,r.lane,r.lanes]),[[1,0,2],[2,1,2],[3,0,2],[4,0,1]]);
});
test('time ranges are explicit and cross noon correctly',() => {
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../app/static/api.js'),'utf8'),context);
  assert.equal(context.timeRange('09:00'),'9:00 AM – 10:00 AM');
  assert.equal(context.timeRange('11:00'),'11:00 AM – 12:00 PM');
  assert.equal(context.timeRange('13:00','14:00'),'1:00 PM – 2:00 PM');
});

test('doctor calendar renders bookings, navigates, opens details, and refreshes new arrivals',async () => {
  class Element {
    constructor() { this.children=[]; this.events={}; this.style={}; this.attributes={}; this.value=''; this.className=''; this.textContent=''; this.classList={toggle:(name,on) => { this.attributes[name]=on; }}; }
    appendChild(child) { this.children.push(child); return child; }
    replaceChildren() { this.children=[]; }
    addEventListener(name,fn) { this.events[name]=fn; }
    setAttribute(name,value) { this.attributes[name]=value; }
    showModal() { this.open=true; }
    close() { this.open=false; }
  }
  const elements = {};
  const dom = {hidden:false, getElementById:id => elements[id] ||= new Element(), createElement:() => new Element(),
    querySelector:() => ({content:'csrf'}),addEventListener() {}};
  let interval;
  const records = [{id:1,reference:'MQ-0001',patient:'Calendar Patient',date:'2026-11-24',time:'09:00',end_time:'10:00',duration_minutes:60,status:'Confirmed',type:'Online'}];
  const scope = vm.createContext({Date,document:dom,window:{addEventListener() {}},setInterval:fn => { interval=fn; },
    fetch:async url => ({ok:true,status:200,json:async () => JSON.parse(JSON.stringify(url === '/api/doctors' ? {today:'2026-11-24'} : url === '/api/blocked-dates' ? {dates:['2026-11-26']} : url === '/api/working-hours' ? {days:Array.from({length:7},(_,weekday) => ({weekday,enabled:weekday<5,start:'09:00',end:'17:00',lunch_start:'12:00',lunch_end:'13:00'}))} : {appointments:records}))})});
  for(const script of ['api.js','doctor-calendar.js','doctor.js']) vm.runInContext(fs.readFileSync(path.join(__dirname,'../app/static',script),'utf8'),scope);
  const settle = async () => { await new Promise(setImmediate); await new Promise(setImmediate); };
  const descendants = node => [node,...node.children.flatMap(descendants)];
  const cards = () => descendants(elements.calendarGrid).filter(n => n.className.startsWith('calendar-event '));
  await settle();
  assert.equal(elements.calendarGrid.children.length,24);
  assert.equal(cards().length,1);
  assert.equal(cards()[0].style.height,'71px');
  assert.match(cards()[0].attributes['aria-label'],/Calendar Patient.*9:00 AM – 10:00 AM/);
  assert.equal(elements.calendarSummary.textContent,'1 appointment this week');
  assert.equal(descendants(elements.calendarGrid).some(n => n.textContent === 'Unavailable'),true);
  assert.equal(descendants(elements.calendarGrid).some(n => n.textContent === 'Not working'),true);
  assert.equal(descendants(elements.calendarGrid).some(n => n.textContent === 'Lunch · 12:00 PM – 1:00 PM'),true);
  cards()[0].events.click();
  assert.equal(elements.appointmentDialog.open,true);
  assert.equal(elements.appointmentTitle.textContent,'Calendar Patient');
  assert.match(elements.appointmentDetails.textContent,/1 hour/);
  elements.closeAppointment.events.click();
  assert.equal(elements.appointmentDialog.open,false);
  records.push({...records[0],id:2,reference:'MQ-0002',patient:'New Arrival',date:'2026-11-27',time:'11:00',end_time:'12:00'});
  interval(); await settle();
  assert.equal(cards().length,2);
  assert.equal(cards().some(n => n.children[0].textContent === 'New Arrival'),true);
  elements.nextPeriod.events.click(); await settle();
  assert.match(elements.calendarTitle.textContent,/Nov 30.*Dec 6/);
  assert.equal(cards().length,0);
  elements.todayButton.events.click(); await settle();
  records[0].status='Cancelled';
  records.push({...records[0],id:3,reference:'MQ-0003',patient:'Short Consultation',status:'Confirmed',date:'2026-11-24',time:'10:00',end_time:'10:30',duration_minutes:30});
  interval(); await settle();
  const cancelledCard=cards().find(card => card.children[0].textContent === 'Calendar Patient');
  assert.match(cancelledCard.className,/cancelled/);
  assert.match(elements.calendarSummary.textContent,/1 cancelled/);
  assert.match(elements.queue.children[0].children[0].textContent,/Cancelled appointment/);
  assert.equal(elements.waiting.textContent,1);
  const shortCard=cards().find(card => card.children[0].textContent === 'Short Consultation');
  assert.equal(shortCard.style.height,'33.5px');
  shortCard.events.click();
  assert.match(elements.appointmentDetails.textContent,/30 minutes/);
  elements.closeAppointment.events.click();
  elements.dayView.events.click();
  assert.equal(elements.calendarGrid.children.length,6);
  assert.equal(elements.dayView.attributes['aria-pressed'],'true');
  assert.equal(cards().length,2);
  assert.equal(elements.previousPeriod.attributes['aria-label'],'Previous day');
  elements.queueTab.events.click();
  assert.equal(elements.calendarPanel.hidden,true);
  assert.equal(elements.queuePanel.hidden,false);
  assert.equal(elements.queueTab.attributes['aria-selected'],'true');
  elements.calendarTab.events.click();
  assert.equal(elements.calendarPanel.hidden,false);
  assert.equal(elements.queuePanel.hidden,true);
  const appointmentButtons=elements.queue.children.find(row => row.children[0].textContent.includes('Short Consultation')).children.slice(1);
  assert.equal(appointmentButtons[0].disabled,true);
});
