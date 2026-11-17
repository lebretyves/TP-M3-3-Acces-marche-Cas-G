'use strict';
// Notification-only worker. No fetch handler, offline cache, storage or health API.
const messages=Object.freeze({pause:'Un rappel de pause est disponible.',advice:'Un nouveau conseil est disponible dans votre espace.',report:'Un bilan est disponible dans votre espace.',support:'Une réponse du support est disponible.',calibration:'Une vérification de calibration est nécessaire.'});
self.addEventListener('push',event=>{
 let payload;try{payload=event.data?.json();}catch{return;}
 if(!payload||!Object.prototype.hasOwnProperty.call(messages,payload.kind))return;
 event.waitUntil(self.registration.showNotification('SKELIVIA',{body:messages[payload.kind],icon:'/static/skelivia-logo-original.png',tag:'skelivia-'+payload.kind,silent:payload.silent===true,data:{url:'/?notifications=1'}}));
});
self.addEventListener('notificationclick',event=>{
 event.notification.close();
 event.waitUntil((async()=>{const windows=await self.clients.matchAll({type:'window',includeUncontrolled:true});const existing=windows.find(client=>{const url=new URL(client.url);return url.origin===self.location.origin&&url.pathname==='/';});if(existing){await existing.focus();existing.postMessage({type:'SKELIVIA_OPEN_NOTIFICATIONS'});return;}await self.clients.openWindow('/?notifications=1');})());
});
