"""Minimal new-browser signal. This is not a second authentication factor."""
import hashlib
import secrets
import time
from sqlalchemy import delete
from .models import LoginDevice
from .database import configure_actor


def record_login(db,actor,request,response,*,secure):
    cookie=request.cookies.get('skelivia_browser','')
    if len(cookie)!=43 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in cookie):
        cookie=secrets.token_urlsafe(32)
    key=hashlib.sha256((actor.id+':'+cookie).encode()).hexdigest()
    known=db.get(LoginDevice,key)
    now=time.time()
    db.execute(delete(LoginDevice).where(LoginDevice.last_seen<now-30*86400))
    if known: known.last_seen=now
    else:
        db.add(LoginDevice(digest=key,user_id=actor.id,last_seen=now))
        if actor.role in {'user','clinician'}:
            from .domain import notify
            configure_actor(db,actor)
            notify(db,actor.id,'security','Connexion depuis un nouveau navigateur','settings')
    response.set_cookie('skelivia_browser',cookie,httponly=True,secure=secure,samesite='lax' if secure else 'strict',max_age=30*86400,path='/')
    db.commit()
