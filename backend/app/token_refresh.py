"""Google token renewal; credentials never leave the backend."""
import asyncio
import json
import logging
import os
import secrets
import time

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import ForeignKey, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from .main import Base
from .oauth import LinkedAccount

logger = logging.getLogger(__name__)
REFRESH_WINDOW = 300


class RefreshState(Base):
    __tablename__ = 'oauth_refresh_states'
    connection_id: Mapped[int] = mapped_column(ForeignKey('linked_accounts.id'), primary_key=True)
    status: Mapped[str] = mapped_column(default='ready')
    retry_at: Mapped[int] = mapped_column(default=0)
    failures: Mapped[int] = mapped_column(default=0)
    lease_until: Mapped[int] = mapped_column(default=0)
    lease_token: Mapped[str] = mapped_column(default='')


MESSAGES = {
    'ready': 'Connected. The backend renews Google access tokens automatically.',
    'reconnect_required': 'Google offline access is missing, expired, or revoked. Reconnect this account to authorize automatic refresh.',
    'temporary_error': 'Google could not be reached or temporarily rejected renewal. The backend will retry automatically.',
    'configuration_error': 'Automatic refresh needs valid Google client credentials and the original encryption key. Check backend settings and restart it.',
}


def encryption():
    return Fernet(os.environ['TOKEN_ENCRYPTION_KEY'].encode())


def refresh_details(account, session):
    if account.provider != 'google':
        return {'automatic_refresh': False, 'refresh_status': 'not_supported', 'reconnect_required': account.expires_at <= time.time()}
    state = session.get(RefreshState, account.id)
    try:
        tokens = json.loads(encryption().decrypt(account.encrypted_tokens.encode()))
        available = bool(tokens.get('refresh_token'))
        status = state.status if state else 'ready'
        if not available:
            status = 'reconnect_required'
        elif not os.getenv('GOOGLE_CLIENT_ID') or not os.getenv('GOOGLE_CLIENT_SECRET'):
            status = 'configuration_error'
    except (KeyError, ValueError, TypeError, InvalidToken):
        available, status = False, 'configuration_error'
    return {'automatic_refresh': available and status in ('ready', 'temporary_error'), 'refresh_status': status,
            'reconnect_required': status == 'reconnect_required', 'refresh_message': MESSAGES[status],
            'retry_at': state.retry_at if state and status in ('temporary_error', 'configuration_error') else None}


async def refresh_google_account(factory, account_id):
    """Renew if due. A database lease and compare-and-swap protect concurrent workers/reconnects."""
    with factory() as session:
        now = int(time.time())
        account = session.get(LinkedAccount, account_id)
        if not account or account.provider != 'google' or account.expires_at > now + REFRESH_WINDOW:
            return False
        state = session.get(RefreshState, account_id)
        if state is None:
            session.add(RefreshState(connection_id=account_id))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
        lease = secrets.token_urlsafe(16)
        acquired = session.execute(update(RefreshState).where(
            RefreshState.connection_id == account_id, RefreshState.lease_until <= now,
            RefreshState.retry_at <= now, RefreshState.status != 'reconnect_required',
        ).values(lease_until=now+30, lease_token=lease))
        session.commit()
        if acquired.rowcount != 1:
            return False
        account = session.get(LinkedAccount, account_id)
        if not account:
            return False
        original = account.encrypted_tokens
        session.commit()  # Do not hold a database transaction during the provider request.
        status, new_tokens, new_expiry = 'configuration_error', None, None
        retry_after = 0
        try:
            crypto = encryption()
            tokens = json.loads(crypto.decrypt(original.encode()))
            refresh = tokens.get('refresh_token')
            client_id, client_secret = os.getenv('GOOGLE_CLIENT_ID'), os.getenv('GOOGLE_CLIENT_SECRET')
            if not isinstance(refresh, str) or not refresh:
                status = 'reconnect_required'
            elif client_id and client_secret:
                try:
                    async with httpx.AsyncClient(timeout=8) as client:
                        response = await client.post('https://oauth2.googleapis.com/token', data={
                            'grant_type':'refresh_token', 'refresh_token':refresh,
                            'client_id':client_id, 'client_secret':client_secret,
                        })
                    data = response.json()
                    if data.get('error') == 'invalid_grant':
                        status = 'reconnect_required'
                    elif response.status_code == 429 or response.status_code >= 500 or response.status_code == 408:
                        status = 'temporary_error'
                        try:
                            retry_after = max(0, min(3600, int(response.headers.get('Retry-After', '0'))))
                        except ValueError:
                            pass
                    elif not response.is_success or data.get('error'):
                        status = 'configuration_error'
                    else:
                        access, lifetime = data['access_token'], int(data['expires_in'])
                        if not isinstance(access, str) or not access or lifetime <= 0:
                            raise ValueError('Malformed refresh response')
                        # Google normally omits refresh_token on renewal; keep the working one.
                        rotated = data.get('refresh_token') or refresh
                        if not isinstance(rotated, str):
                            raise ValueError('Malformed refresh token')
                        new_tokens = crypto.encrypt(json.dumps({**tokens, 'access_token':access,
                                                               'refresh_token':rotated,
                                                               'token_type':data.get('token_type', tokens.get('token_type','Bearer'))}).encode()).decode()
                        new_expiry, status = int(time.time())+lifetime, 'ready'
                except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
                    status = 'temporary_error'
        except (KeyError, ValueError, TypeError, InvalidToken):
            status = 'configuration_error'
        # A user may have disconnected or reauthorized while the HTTP request was running.
        session.expire_all()
        current = session.get(LinkedAccount, account_id)
        if current is None or current.encrypted_tokens != original:
            session.execute(update(RefreshState).where(RefreshState.connection_id == account_id,
                                                       RefreshState.lease_token == lease).values(lease_until=0, lease_token=''))
            session.commit()
            return False
        if status == 'ready':
            updated = session.execute(update(LinkedAccount).where(LinkedAccount.id == account_id,
                                                                  LinkedAccount.encrypted_tokens == original).values(
                                                                      encrypted_tokens=new_tokens, expires_at=new_expiry))
            if updated.rowcount != 1:
                session.rollback()
                return False
        state = session.get(RefreshState, account_id)
        failures = state.failures+1 if state and status != 'ready' else 0
        delay = max(retry_after, min(300, 30 * (2 ** min(failures, 4)))) if status == 'temporary_error' else 600
        session.execute(update(RefreshState).where(RefreshState.connection_id == account_id,
                                                   RefreshState.lease_token == lease).values(
            status=status, failures=failures, lease_until=0, lease_token='',
            retry_at=int(time.time())+delay if status in ('temporary_error','configuration_error') else 0))
        session.commit()
        return status == 'ready'


async def refresh_due_accounts(factory):
    with factory() as session:
        ids = list(session.scalars(select(LinkedAccount.id).where(LinkedAccount.provider == 'google',
                                  LinkedAccount.expires_at <= int(time.time())+REFRESH_WINDOW)))
    limit = asyncio.Semaphore(3)
    async def renew(account_id):
        async with limit:
            try:
                await refresh_google_account(factory, account_id)
            except Exception as exc:
                # Never log HTTP payloads, credentials, or exception messages that may contain them.
                logger.error('Google refresh failed for connection %s (%s)', account_id, type(exc).__name__)
    await asyncio.gather(*(renew(account_id) for account_id in ids))


async def refresh_worker(factory):
    while True:
        try:
            await refresh_due_accounts(factory)
        except Exception as exc:
            logger.error('Google refresh scan failed (%s)', type(exc).__name__)
        await asyncio.sleep(60)
