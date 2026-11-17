"""Confidential OIDC code flow. Browser receives only an opaque local session."""
import base64
import hashlib
import hmac
import os
import secrets
import ssl
import time
import logging
from pathlib import Path
from urllib.parse import urlencode, parse_qs
import httpx
import jwt
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from .models import Account, Audit, OIDCIdentity, OIDCState, WebSession, LogoutReplay


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Provider:
    def __init__(self):
        self.issuer = os.environ['SKELIVIA_OIDC_ISSUER'].rstrip('/')
        self.internal = os.environ.get('SKELIVIA_OIDC_INTERNAL_BASE', self.issuer).rstrip('/')
        if not self.issuer.startswith('https://') or not self.internal.startswith('https://'):
            raise RuntimeError('OIDC requires verified HTTPS endpoints.')
        self.client_id = os.getenv('SKELIVIA_OIDC_CLIENT_ID', 'skelivia-web')
        self.secret_file = Path(os.environ['SKELIVIA_OIDC_CLIENT_SECRET_FILE'])
        self.ca = os.getenv('SKELIVIA_CA_FILE')
        self.acr = os.getenv('SKELIVIA_OIDC_REQUIRED_ACR', '2')

    def client(self):
        context = ssl.create_default_context(cafile=self.ca)
        return httpx.Client(verify=context, timeout=10, follow_redirects=False, trust_env=False)

    def local_endpoint(self, value):
        if not isinstance(value, str) or not value.startswith(self.issuer + '/'):
            raise ValueError('Provider endpoint outside pinned issuer.')
        return self.internal + value[len(self.issuer):]

    def discovery(self):
        with self.client() as client:
            response = client.get(self.internal+'/.well-known/openid-configuration')
            response.raise_for_status()
            metadata = response.json()
        if metadata.get('issuer') != self.issuer:
            raise ValueError('Issuer mismatch.')
        for name in ('authorization_endpoint','token_endpoint','jwks_uri'):
            self.local_endpoint(metadata.get(name))
        return metadata

    def verify(self, token, metadata, *, nonce=None, logout=False):
        header = jwt.get_unverified_header(token)
        if header.get('alg') != 'RS256' or not isinstance(header.get('kid'), str):
            raise ValueError('Signing algorithm refused.')
        with self.client() as client:
            response = client.get(self.local_endpoint(metadata['jwks_uri']))
            response.raise_for_status()
            keys = response.json().get('keys', [])
        matches = [key for key in keys if key.get('kid')==header['kid'] and key.get('kty')=='RSA' and key.get('use','sig')=='sig' and key.get('alg','RS256')=='RS256']
        if len(matches) != 1:
            raise ValueError('Unknown signing key.')
        required = ['iss','aud','iat','jti'] if logout else ['iss','aud','exp','iat','sub','nonce','auth_time','acr']
        claims = jwt.decode(token,jwt.PyJWK.from_dict(matches[0]).key,algorithms=['RS256'],audience=self.client_id,issuer=self.issuer,leeway=10,options={'require':required})
        now = time.time()
        if logout:
            if any(key in claims and (not isinstance(claims[key],str) or not 1<=len(claims[key])<=200) for key in ('jti','sub','sid')):
                raise ValueError('Invalid logout identifiers.')
            if now-claims['iat']>120 or 'nonce' in claims or claims.get('events') != {'http://schemas.openid.net/event/backchannel-logout':{}}:
                raise ValueError('Invalid logout claims.')
            if not claims.get('sub') and not claims.get('sid'):
                raise ValueError('Logout subject missing.')
        else:
            if claims.get('azp', self.client_id) != self.client_id:
                raise ValueError('Authorized party mismatch.')
            if not hmac.compare_digest(str(claims['nonce']), nonce or ''):
                raise ValueError('Nonce mismatch.')
            if str(claims['acr']) != self.acr or not isinstance(claims['auth_time'], (int,float)) or now-claims['auth_time']>300 or claims['auth_time']>now+10:
                raise ValueError('Recent multifactor authentication required.')
        return claims


def install_oidc(app, factory, issue, session_json, cookie, origin):
    provider = Provider()
    redirect_uri = origin+'/oidc/callback'
    app.state.oidc_provider = provider

    @app.get('/oidc/login')
    def login(request:Request,return_to:str='/'):
        # A fixed allowlist, not a URL or arbitrary relative path. The selected
        # target is bound into the one-use server-side state's hash below.
        if return_to not in {'/','/simulateur/'} or len(request.query_params.getlist('return_to'))>1:
            raise HTTPException(400,'Destination de retour non autorisée.')
        try:
            metadata = provider.discovery()
        except (ValueError,httpx.HTTPError,KeyError):
            raise HTTPException(503,'Service d’identité indisponible.') from None
        raw_state,nonce,verifier = (secrets.token_urlsafe(32) for _ in range(3))
        raw_state=('simulator.' if return_to=='/simulateur/' else 'default.')+raw_state
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        params={'response_type':'code','client_id':provider.client_id,'redirect_uri':redirect_uri,'scope':'openid','state':raw_state,'nonce':nonce,'code_challenge':challenge,'code_challenge_method':'S256','acr_values':provider.acr,'max_age':'0'}
        response=RedirectResponse(metadata['authorization_endpoint']+'?'+urlencode(params),status_code=302)
        with factory() as db:
            db.execute(delete(OIDCState).where(OIDCState.expires<time.time()))
            # A fresh browser-binding session also prevents login CSRF/account swapping.
            previous=request.cookies.get(cookie)
            if previous: db.execute(delete(WebSession).where(WebSession.token_hash==digest(previous)))
            session=issue(db,response)
            db.add(OIDCState(digest=digest(raw_state),session_hash=session.token_hash,nonce=nonce,verifier=verifier,expires=time.time()+300))
            db.commit()
        return response

    @app.get('/oidc/callback')
    def callback(request:Request,state:str='',code:str='',error:str=''):
        if error or not state or not code or len(state)>200 or len(code)>4096:
            raise HTTPException(400,'Authentification interrompue ou réponse invalide.')
        with factory() as db:
            pending=db.get(OIDCState,digest(state))
            binding=digest(request.cookies.get(cookie,''))
            if not pending or pending.expires<time.time() or not hmac.compare_digest(pending.session_hash,binding):
                raise HTTPException(400,'Tentative de connexion expirée ou invalide.')
            nonce,verifier=pending.nonce,pending.verifier
            # Only use this routing hint after the complete state hash and
            # browser binding have matched. Callback query strings cannot set it.
            return_to='/simulateur/' if state.startswith('simulator.') else '/'
            # Atomically consume the state before the external token exchange.
            deleted=db.execute(delete(OIDCState).where(OIDCState.digest==pending.digest))
            db.commit()
            if deleted.rowcount!=1: raise HTTPException(400,'Tentative déjà utilisée.')
        try:
            metadata=provider.discovery()
            with provider.client() as client:
                response=client.post(provider.local_endpoint(metadata['token_endpoint']),data={'grant_type':'authorization_code','code':code,'redirect_uri':redirect_uri,'code_verifier':verifier},auth=(provider.client_id,provider.secret_file.read_text().strip()))
                response.raise_for_status()
                tokens=response.json()
            claims=provider.verify(tokens['id_token'],metadata,nonce=nonce)
        except (ValueError,KeyError,httpx.HTTPError,jwt.PyJWTError) as failure:
            # Operator diagnosis includes no code, token, nonce, subject or request body.
            category=type(failure).__name__
            if isinstance(failure,jwt.MissingRequiredClaimError): category+=':'+failure.claim
            elif type(failure) is ValueError and str(failure) in {'Recent multifactor authentication required.','Nonce mismatch.','Issuer mismatch.','Authorized party mismatch.','Unknown signing key.'}: category+=':'+str(failure)
            elif isinstance(failure,httpx.HTTPStatusError): category+=':'+str(failure.response.status_code)
            logging.getLogger('skelivia.auth').warning('OIDC authentication refused (%s)',category)
            with factory.begin() as db:
                db.add(Audit(at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),event='oidc_refusee',actor_id='anonyme',result='refus'))
            raise HTTPException(401,'Identité ou authentification renforcée non vérifiée.') from None
        with factory() as db:
            identity=db.get(OIDCIdentity,claims['sub'])
            account=db.get(Account,identity.user_id) if identity else None
            if not account or not account.active:
                raise HTTPException(403,'Compte non habilité pour ce service.')
            db.execute(delete(WebSession).where(WebSession.token_hash==binding))
            result=RedirectResponse(return_to,status_code=303)
            issue(db,result,account.id,auth_time=claims['auth_time'],oidc_sid=claims.get('sid'))
            from .login_activity import record_login
            record_login(db,account,request,result,secure=True)
            db.add(Audit(at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),event='connexion_oidc_mfa',actor_id=account.id,result='ok'))
            db.commit()
        return result

    @app.post('/oidc/backchannel-logout')
    async def backchannel(request:Request):
        raw=await request.body()
        if len(raw)>16384: raise HTTPException(413,'Request too large.')
        try:
            token=parse_qs(raw.decode('utf-8'),strict_parsing=True).get('logout_token',[])
            if len(token)!=1: raise ValueError('Missing token.')
            claims=provider.verify(token[0],provider.discovery(),logout=True)
        except (ValueError,KeyError,UnicodeError,httpx.HTTPError,jwt.PyJWTError):
            raise HTTPException(400,'Invalid logout token.') from None
        with factory() as db:
            db.execute(delete(LogoutReplay).where(LogoutReplay.expires<time.time()))
            db.add(LogoutReplay(jti=claims['jti'],expires=time.time()+300))
            try: db.flush()
            except IntegrityError:
                db.rollback()
                return JSONResponse({'ok':True})
            query=delete(WebSession)
            if claims.get('sid'): query=query.where(WebSession.oidc_sid==claims['sid'])
            else:
                identity=db.get(OIDCIdentity,claims['sub'])
                if not identity: db.commit();return JSONResponse({'ok':True})
                query=query.where(WebSession.user_id==identity.user_id)
            db.execute(query);db.commit()
        return JSONResponse({'ok':True})
