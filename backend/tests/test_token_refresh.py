import asyncio
import json
from types import SimpleNamespace
from urllib.parse import parse_qs

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from app import main, token_refresh as renewal
from app.oauth import LinkedAccount


@pytest.fixture
def store(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'refresh.db'}", connect_args={'check_same_thread':False})
    main.Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    key = Fernet.generate_key()
    monkeypatch.setenv('TOKEN_ENCRYPTION_KEY', key.decode())
    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'test-client')
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET', 'test-secret')
    clock = [2000000000]
    monkeypatch.setattr(renewal, 'time', SimpleNamespace(time=lambda: clock[0]))
    tokens = {'access_token':'old-access', 'refresh_token':'old-refresh', 'token_type':'Bearer'}
    with factory() as session:
        item = LinkedAccount(influencer_id=1, provider='google', account_id='123',display_name='Demo',
                             encrypted_tokens=Fernet(key).encrypt(json.dumps(tokens).encode()).decode(),
                             expires_at=clock[0]+60,scopes='openid email profile')
        session.add(item); session.commit(); account_id=item.id
    yield factory, key, clock, account_id
    engine.dispose()


def transport(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(renewal.httpx, 'AsyncClient', lambda **kwargs: real(transport=httpx.MockTransport(handler), **kwargs))


def read(factory, key, account_id):
    with factory() as session:
        account = session.get(LinkedAccount, account_id)
        return account.expires_at, json.loads(Fernet(key).decrypt(account.encrypted_tokens.encode()))


def test_refresh_preserves_refresh_token_and_updates_expiry(store, monkeypatch):
    factory,key,clock,account_id=store
    def handler(request):
        assert str(request.url)=='https://oauth2.googleapis.com/token'
        body=parse_qs(request.content.decode())
        assert body=={'grant_type':['refresh_token'],'refresh_token':['old-refresh'],'client_id':['test-client'],'client_secret':['test-secret']}
        return httpx.Response(200,json={'access_token':'new-access','expires_in':3600})
    transport(monkeypatch,handler)
    assert asyncio.run(renewal.refresh_google_account(factory,account_id)) is True
    expiry,tokens=read(factory,key,account_id)
    assert expiry==clock[0]+3600
    assert tokens['access_token']=='new-access' and tokens['refresh_token']=='old-refresh'
    with factory() as session:
        item=session.get(LinkedAccount,account_id)
        assert 'new-access' not in item.encrypted_tokens
        status=renewal.refresh_details(item,session)
        assert status['automatic_refresh'] is True and status['reconnect_required'] is False
        assert 'old-refresh' not in str(status)
        assert session.get(renewal.RefreshState,account_id).status=='ready'


def test_not_due_does_not_call_provider(store,monkeypatch):
    factory,_,clock,account_id=store
    with factory() as session:
        session.get(LinkedAccount,account_id).expires_at=clock[0]+3600
        session.commit()
    def handler(request): raise AssertionError('Healthy token should not refresh')
    transport(monkeypatch,handler)
    assert asyncio.run(renewal.refresh_google_account(factory,account_id)) is False


def test_revoked_grant_requires_reconnection_without_retries(store,monkeypatch):
    factory,key,_,account_id=store
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(400,json={'error':'invalid_grant','error_description':'sensitive provider text'})
    transport(monkeypatch,handler)
    assert asyncio.run(renewal.refresh_google_account(factory,account_id)) is False
    assert asyncio.run(renewal.refresh_google_account(factory,account_id)) is False
    assert len(calls)==1
    assert read(factory,key,account_id)[1]['refresh_token']=='old-refresh'
    with factory() as session:
        status=renewal.refresh_details(session.get(LinkedAccount,account_id),session)
        assert status['reconnect_required'] is True and status['automatic_refresh'] is False
        assert 'sensitive provider text' not in str(status)


def test_temporary_failure_retries_and_accepts_rotated_token(store,monkeypatch):
    factory,key,clock,account_id=store
    calls=[]
    def handler(request):
        calls.append(request)
        if len(calls)==1:
            return httpx.Response(503,json={'error':'temporarily_unavailable'})
        return httpx.Response(200,json={'access_token':'new-access','refresh_token':'rotated-refresh','expires_in':3600})
    transport(monkeypatch,handler)
    assert asyncio.run(renewal.refresh_google_account(factory,account_id)) is False
    with factory() as session:
        state=session.get(renewal.RefreshState,account_id)
        assert state.status=='temporary_error' and state.retry_at>clock[0]
        retry=state.retry_at
    assert asyncio.run(renewal.refresh_google_account(factory,account_id)) is False
    assert len(calls)==1
    clock[0]=retry+1
    assert asyncio.run(renewal.refresh_google_account(factory,account_id)) is True
    assert read(factory,key,account_id)[1]['refresh_token']=='rotated-refresh'


def test_database_lease_prevents_simultaneous_refresh(store,monkeypatch):
    factory,_,_,account_id=store
    async def scenario():
        entered,release=asyncio.Event(),asyncio.Event()
        calls=[]
        async def handler(request):
            calls.append(request); entered.set(); await release.wait()
            return httpx.Response(200,json={'access_token':'new','expires_in':3600})
        transport(monkeypatch,handler)
        first=asyncio.create_task(renewal.refresh_google_account(factory,account_id))
        await entered.wait()
        assert await renewal.refresh_google_account(factory,account_id) is False
        release.set()
        assert await first is True
        assert len(calls)==1
    asyncio.run(scenario())


@pytest.mark.parametrize('action',['disconnect','reconnect'])
def test_inflight_refresh_does_not_restore_disconnected_or_overwrite_reconnected_account(store,monkeypatch,action):
    factory,key,clock,account_id=store
    def handler(request):
        with factory() as session:
            session.execute(delete(renewal.RefreshState).where(renewal.RefreshState.connection_id==account_id))
            item=session.get(LinkedAccount,account_id)
            if action=='disconnect': session.delete(item)
            else:
                item.encrypted_tokens=Fernet(key).encrypt(json.dumps({'access_token':'reauthorized','refresh_token':'new-grant'}).encode()).decode()
                item.expires_at=clock[0]+7200
            session.commit()
        return httpx.Response(200,json={'access_token':'stale-result','expires_in':3600})
    transport(monkeypatch,handler)
    assert asyncio.run(renewal.refresh_google_account(factory,account_id)) is False
    with factory() as session:
        assert session.get(renewal.RefreshState,account_id) is None
        if action=='disconnect': assert session.get(LinkedAccount,account_id) is None
    if action=='reconnect': assert read(factory,key,account_id)[1]['access_token']=='reauthorized'


def test_missing_refresh_token_and_invalid_configuration(store,monkeypatch):
    factory,key,_,account_id=store
    with factory() as session:
        session.get(LinkedAccount,account_id).encrypted_tokens=Fernet(key).encrypt(json.dumps({'access_token':'old'}).encode()).decode()
        session.commit()
    def handler(request): raise AssertionError('Must not request with missing refresh token')
    transport(monkeypatch,handler)
    assert asyncio.run(renewal.refresh_google_account(factory,account_id)) is False
    with factory() as session:
        assert session.get(renewal.RefreshState,account_id).status=='reconnect_required'
        session.delete(session.get(renewal.RefreshState,account_id)); session.commit()
    monkeypatch.setenv('TOKEN_ENCRYPTION_KEY','invalid-key')
    assert asyncio.run(renewal.refresh_google_account(factory,account_id)) is False
    with factory() as session:
        assert session.get(renewal.RefreshState,account_id).status=='configuration_error'


def test_background_scan_renews_overdue_tokens_after_restart(store,monkeypatch):
    factory,key,clock,account_id=store
    with factory() as session:
        session.get(LinkedAccount,account_id).expires_at=clock[0]-3600
        session.commit()
    transport(monkeypatch,lambda request: httpx.Response(200,json={'access_token':'renewed','expires_in':3600}))
    asyncio.run(renewal.refresh_due_accounts(factory))
    assert read(factory,key,account_id)[0]==clock[0]+3600
