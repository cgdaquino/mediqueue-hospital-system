let latestActionNotice=0;
function recentActionNotice() { return Date.now()-latestActionNotice < 2000; }
const noticeRegion=document.createElement('div'); noticeRegion.className='notice-region';
noticeRegion.setAttribute('aria-label','Action notifications'); noticeRegion.setAttribute('aria-live','polite');
document.body.appendChild(noticeRegion);
function notifyAction(message,undo) {
  latestActionNotice=Date.now();
  const card=document.createElement('div'); card.className='action-notice'; card.setAttribute('role','status');
  const text=document.createElement('span'); text.textContent=message; card.appendChild(text);
  let timer,expiry;
  const remove=() => { clearInterval(timer); clearTimeout(expiry); card.remove(); };
  if(undo) {
    const button=document.createElement('button'); button.type='button';
    const update=() => {
      const left=Math.max(0,Math.ceil((undo.expires_at*1000-Date.now())/1000));
      button.textContent=`Undo (${left}s)`; if(!left) remove();
    };
    button.addEventListener('click',async () => {
      button.disabled=true; clearInterval(timer); clearTimeout(expiry);
      try { await api(`/api/actions/${undo.token}/undo`,{method:'POST'}); remove(); }
      catch(error) { text.textContent=error.message; button.remove(); expiry=setTimeout(remove,5000); }
    });
    card.appendChild(button); timer=setInterval(update,100); update();
  }
  noticeRegion.appendChild(card);
  expiry=setTimeout(remove,undo ? Math.max(0,undo.expires_at*1000-Date.now()) : 5000);
}
