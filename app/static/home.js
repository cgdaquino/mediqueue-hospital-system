const portalCards=Array.from(document.querySelectorAll('[data-portal]'));
const backgroundScenes=Array.from(document.querySelectorAll('[data-scene]'));
let hoveredPortal=null;
function displayScene(name) {
  backgroundScenes.forEach(scene => scene.classList.toggle('is-active',scene.dataset.scene === name));
}
function focusedPortal(target=document.activeElement) {
  return portalCards.find(card => card.contains(target))?.dataset.portal;
}
portalCards.forEach(card => {
  card.addEventListener('pointerenter',event => {
    if(event.pointerType === 'touch') return;
    hoveredPortal=card.dataset.portal; displayScene(hoveredPortal);
  });
  card.addEventListener('pointerleave',() => {
    hoveredPortal=null; displayScene(focusedPortal() || 'hospital');
  });
  card.addEventListener('focusin',() => displayScene(card.dataset.portal));
  card.addEventListener('focusout',event => displayScene(focusedPortal(event.relatedTarget) || hoveredPortal || 'hospital'));
});
