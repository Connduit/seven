"""Read-only account linking through official Google, TikTok and Snap OAuth APIs."""
import base64
import hashlib
import json
import os
import secrets
import time
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import UniqueConstraint, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .main import Base, db, find
from .instagram import admin, digest

PROVIDERS = {
    'google': {
        'name': 'Google', 'prefix': 'GOOGLE', 'scope': 'openid email profile',
        'authorize': 'https://accounts.google.com/o/oauth2/v2/auth',
        'token': 'https://oauth2.googleapis.com/token',
        'description': 'Google identity only. Does not access Gmail, Drive, or YouTube.',
    },
    'tiktok': {
        'name': 'TikTok', 'prefix': 'TIKTOK', 'scope': 'user.info.basic',
        'authorize': 'https://www.tiktok.com/v2/auth/authorize/',
        'token': 'https://open.tiktokapis.com/v2/oauth/token/',
        'description': 'Basic TikTok profile only. Does not upload or publish videos.',
    },
    'snapchat': {
        'name': 'Snapchat', 'prefix': 'SNAPCHAT',
        'scope': 'https://auth.snapchat.com/oauth2/api/user.display_name',
        'authorize': 'https://accounts.snapchat.com/accounts/oauth2/auth',
        'token': 'https://accounts.snapchat.com/accounts/oauth2/token',
        'description': 'Snap Login Kit identity only. Does not read chats or publish Stories.',
    },
}
router = APIRouter(prefix='/api')


class LinkedAccount(Base):
    __tablename__ = 'linked_accounts'
    __table_args__ = (UniqueConstraint('provider', 'account_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    influencer_id: Mapped[int] = mapped_column(index=True)
    provider: Mapped[str]
    account_id: Mapped[str]
    display_name: Mapped[str]
    encrypted_tokens: Mapped[str]
    expires_at: Mapped[int]
    scopes: Mapped[str]


class LinkAttempt(Base):
    __tablename__ = 'account_link_attempts'
    state_hash: Mapped[str] = mapped_column(primary_key=True)
    provider: Mapped[str]
    influencer_id: Mapped[int]
    encrypted_verifier: Mapped[str]
    expires_at: Mapped[int]


def provider_config(provider):
    if provider not in PROVIDERS:
        raise HTTPException(404, 'Unsupported OAuth provider')
    info = PROVIDERS[provider]
    prefix = info['prefix']
    names = [f'{prefix}_CLIENT_ID', f'{prefix}_CLIENT_SECRET', f'{prefix}_REDIRECT_URI', 'STUDIO_ADMIN_KEY', 'TOKEN_ENCRYPTION_KEY']
    missing = [name for name in names if not os.getenv(name)]
    if missing:
        raise HTTPException(503, 'Set ' + ', '.join(missing))
    try:
        Fernet(os.environ['TOKEN_ENCRYPTION_KEY'].encode())
        redirect = urlsplit(os.environ[f'{prefix}_REDIRECT_URI'])
        frontend = urlsplit(os.getenv('STUDIO_FRONTEND_URL', 'http://localhost:5173'))
        local_google = provider == 'google' and redirect.scheme == 'http' and redirect.hostname in ('localhost', '127.0.0.1')
        if (redirect.scheme != 'https' and not local_google) or not redirect.hostname or redirect.username or redirect.password or redirect.query or redirect.fragment:
            raise ValueError()
        if redirect.path != f'/api/integrations/{provider}/callback':
            raise ValueError()
        if (frontend.scheme, frontend.netloc) != (redirect.scheme, redirect.netloc) or frontend.username or frontend.query or frontend.fragment or frontend.path not in ('', '/'):
            raise ValueError()
        if len(os.environ['STUDIO_ADMIN_KEY']) < 32:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(503, 'Check the encryption/admin keys and callback URL. Dashboard and callback must share one origin. HTTPS is required except Google on localhost.')
    return info, {
        'client_id': os.environ[f'{prefix}_CLIENT_ID'], 'client_secret': os.environ[f'{prefix}_CLIENT_SECRET'],
        'redirect_uri': os.environ[f'{prefix}_REDIRECT_URI'], 'secure': not local_google,
    }


def cipher():
    return Fernet(os.environ['TOKEN_ENCRYPTION_KEY'].encode())


def public(account):
    return {'id': account.id, 'provider': account.provider, 'influencer_id': account.influencer_id,
            'display_name': account.display_name, 'expires_at': account.expires_at,
            'expired': account.expires_at <= time.time(), 'scopes': account.scopes,
            'publishing_available': False}


@router.get('/integrations/oauth/setup')
def setup():
    result = []
    for provider, info in PROVIDERS.items():
        try:
            provider_config(provider)
            configured, message = True, 'Ready to authorize an account.'
        except HTTPException as exc:
            configured, message = False, exc.detail
        result.append({'provider': provider, 'name': info['name'], 'description': info['description'],
                       'configured': configured, 'message': message})
    return result


@router.get('/accounts/connections', dependencies=[Depends(admin)])
def list_connections(response: Response, session: Session = Depends(db)):
    response.headers['Cache-Control'] = 'no-store'
    return [public(a) for a in session.scalars(select(LinkedAccount).order_by(LinkedAccount.id))]


@router.post('/influencers/{influencer_id}/connections/{provider}/connect', dependencies=[Depends(admin)])
def connect(influencer_id: int, provider: str, response: Response, session: Session = Depends(db)):
    info, config = provider_config(provider)
    find(session, influencer_id)
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    session.execute(delete(LinkAttempt).where(LinkAttempt.expires_at <= int(time.time())))
    session.add(LinkAttempt(state_hash=digest(state), provider=provider, influencer_id=influencer_id,
                            encrypted_verifier=cipher().encrypt(verifier.encode()).decode(), expires_at=int(time.time())+600))
    session.commit()
    response.set_cookie('studio_oauth_'+provider, state, max_age=600, httponly=True, secure=config['secure'],
                        samesite='lax', path=f'/api/integrations/{provider}')
    params = {'client_key' if provider == 'tiktok' else 'client_id': config['client_id'],
              'redirect_uri': config['redirect_uri'], 'response_type': 'code', 'scope': info['scope'], 'state': state,
              'code_challenge': challenge, 'code_challenge_method': 'S256'}
    if provider == 'google':
        params.update(access_type='offline', prompt='consent')
    response.headers['Cache-Control'] = 'no-store'
    return {'authorization_url': info['authorize']+'?'+urlencode(params)}


async def exchange(provider, config, code, verifier):
    info = PROVIDERS[provider]
    body = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': config['redirect_uri'], 'code_verifier': verifier}
    options = {}
    if provider == 'snapchat':
        options['auth'] = httpx.BasicAuth(config['client_id'], config['client_secret'])
    else:
        body['client_key' if provider == 'tiktok' else 'client_id'] = config['client_id']
        body['client_secret'] = config['client_secret']
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(info['token'], data=body, **options)
        response.raise_for_status()
        tokens = response.json()
        access = tokens['access_token']
        lifetime = int(tokens['expires_in'])
        if not isinstance(access, str) or not access or lifetime <= 0:
            raise ValueError('Invalid token response')
        headers = {'Authorization': f'Bearer {access}'}
        if provider == 'google':
            identity = await client.get('https://openidconnect.googleapis.com/v1/userinfo', headers=headers)
            identity.raise_for_status()
            user = identity.json()
            account_id, name = user['sub'], user.get('email') or user.get('name') or user['sub']
        elif provider == 'tiktok':
            identity = await client.get('https://open.tiktokapis.com/v2/user/info/', params={'fields':'open_id,display_name'}, headers=headers)
            identity.raise_for_status()
            user = identity.json()['data']['user']
            account_id, name = user['open_id'], user['display_name']
            if tokens.get('open_id') != account_id:
                raise ValueError('TikTok account mismatch')
        else:
            identity = await client.post('https://kit.snapchat.com/v1/me', json={'query':'{me{externalId displayName}}'}, headers=headers)
            identity.raise_for_status()
            user = identity.json()['data']['me']
            account_id, name = user['externalId'], user['displayName']
        if not isinstance(account_id, str) or not account_id or not isinstance(name, str) or not name:
            raise ValueError('Invalid identity')
        # Do not store ID tokens or unrelated response fields.
        saved = {'access_token':access, 'refresh_token':tokens.get('refresh_token'), 'token_type':tokens.get('token_type', 'Bearer')}
        scopes = tokens.get('scope', info['scope'])
        if isinstance(scopes, list):
            scopes = ' '.join(scopes)
        if not isinstance(scopes, str):
            raise ValueError('Invalid scope response')
        return account_id, name, saved, int(time.time())+lifetime, scopes


@router.get('/integrations/{provider}/callback')
async def callback(provider: str, request: Request, session: Session = Depends(db)):
    _, config = provider_config(provider)
    state = request.query_params.get('state', '')
    cookie = request.cookies.get('studio_oauth_'+provider, '')
    if not state or not cookie or not secrets.compare_digest(state, cookie):
        raise HTTPException(400, 'Invalid authorization state. Start a new connection.')
    attempt = session.get(LinkAttempt, digest(state))
    if not attempt or attempt.provider != provider or attempt.expires_at <= time.time():
        raise HTTPException(400, 'Authorization expired or was already used. Start again.')
    influencer_id = attempt.influencer_id
    try:
        verifier = cipher().decrypt(attempt.encrypted_verifier.encode()).decode()
    except (InvalidToken, UnicodeError):
        raise HTTPException(503, 'Authorization key changed. Restore the encryption key or start a new connection.')
    consumed = session.execute(delete(LinkAttempt).where(LinkAttempt.state_hash == digest(state)))
    session.commit()
    if consumed.rowcount != 1:
        raise HTTPException(400, 'Authorization was already used.')
    find(session, influencer_id)
    outcome = 'cancelled'
    if not request.query_params.get('error') and request.query_params.get('code'):
        try:
            account_id, name, tokens, expires, scopes = await exchange(provider, config, request.query_params['code'], verifier)
            existing = session.scalar(select(LinkedAccount).where(LinkedAccount.provider == provider, LinkedAccount.account_id == account_id))
            if existing and existing.influencer_id != influencer_id:
                outcome = 'account_already_linked'
            else:
                encrypted = cipher().encrypt(json.dumps(tokens).encode()).decode()
                if existing:
                    existing.encrypted_tokens, existing.display_name, existing.expires_at, existing.scopes = encrypted, name, expires, scopes
                else:
                    session.add(LinkedAccount(influencer_id=influencer_id, provider=provider, account_id=account_id,
                                              display_name=name, encrypted_tokens=encrypted, expires_at=expires, scopes=scopes))
                session.commit()
                outcome = 'connected'
        except (httpx.HTTPError, KeyError, ValueError, TypeError, IntegrityError):
            session.rollback()
            outcome = 'failed'
    result = RedirectResponse(os.getenv('STUDIO_FRONTEND_URL', 'http://localhost:5173').rstrip('/')+'/?'+urlencode({'oauth':provider,'result':outcome}), status_code=303)
    result.delete_cookie('studio_oauth_'+provider, path=f'/api/integrations/{provider}', secure=config['secure'], httponly=True, samesite='lax')
    result.headers['Cache-Control'] = 'no-store'
    result.headers['Referrer-Policy'] = 'no-referrer'
    return result


@router.delete('/accounts/connections/{account_id}', status_code=204, dependencies=[Depends(admin)])
def disconnect(account_id: int, session: Session = Depends(db)):
    account = session.get(LinkedAccount, account_id)
    if not account:
        raise HTTPException(404, 'Connected account not found')
    session.delete(account)
    session.commit()
