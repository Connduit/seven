import asyncio
import hashlib
import base64
import json
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app import main, oauth


@pytest.fixture
def client(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    main.Base.metadata.create_all(engine)
    def override():
        with Session(engine) as session:
            yield session
    main.app.dependency_overrides[main.db] = override
    key = Fernet.generate_key().decode()
    monkeypatch.setenv('TOKEN_ENCRYPTION_KEY', key)
    monkeypatch.setenv('STUDIO_ADMIN_KEY', 'synthetic-administrator-key-32-characters')
    monkeypatch.setenv('STUDIO_FRONTEND_URL', 'https://testserver')
    for name, info in oauth.PROVIDERS.items():
        monkeypatch.setenv(info['prefix']+'_CLIENT_ID', 'test-id')
        monkeypatch.setenv(info['prefix']+'_CLIENT_SECRET', 'test-secret')
        monkeypatch.setenv(info['prefix']+'_REDIRECT_URI', f'https://testserver/api/integrations/{name}/callback')
    with TestClient(main.app, base_url='https://testserver') as test_client:
        yield test_client, engine, key
    main.app.dependency_overrides.clear()
    engine.dispose()


HEADERS = {'X-Studio-Key':'synthetic-administrator-key-32-characters'}


def create(client, name='Maya'):
    result = client.post('/api/influencers', json={'name':name,'personality':'Curious','interests':'Travel','goal':'Create'})
    assert result.status_code == 201
    return result.json()['id']


def start(client, owner, provider):
    response = client.post(f'/api/influencers/{owner}/connections/{provider}/connect', headers=HEADERS)
    assert response.status_code == 200
    params = parse_qs(urlsplit(response.json()['authorization_url']).query)
    return params['state'][0], params, response


@pytest.mark.parametrize('provider', ['google','tiktok','snapchat'])
def test_callback_connection_encryption_and_disconnect(client, monkeypatch, provider):
    client, engine, key = client
    owner, other = create(client), create(client, 'Jake')
    assert client.post(f'/api/influencers/{owner}/connections/{provider}/connect').status_code == 401
    state, params, response = start(client, owner, provider)
    assert params['code_challenge_method'] == ['S256']
    assert 'Secure' in response.headers['set-cookie'] and 'HttpOnly' in response.headers['set-cookie']
    with Session(engine) as session:
        attempt = session.get(oauth.LinkAttempt, oauth.digest(state))
        verifier = Fernet(key.encode()).decrypt(attempt.encrypted_verifier.encode()).decode()
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        assert params['code_challenge'] == [expected]
        assert attempt.provider == provider and attempt.influencer_id == owner
    async def exchange(actual_provider, config, code, actual_verifier):
        assert actual_provider == provider and code == 'test-code'
        assert len(actual_verifier) >= 43
        return 'account-123', 'Demo account', {'access_token':'private-access','refresh_token':'private-refresh'}, int(time.time())+3600, 'identity'
    monkeypatch.setattr(oauth, 'exchange', exchange)
    callback = f'/api/integrations/{provider}/callback'
    assert client.get(callback, params={'state':'wrong','code':'test-code'}).status_code == 400
    result = client.get(callback, params={'state':state,'code':'test-code'}, follow_redirects=False)
    assert result.status_code == 303 and result.headers['location'].endswith(f'oauth={provider}&result=connected')
    assert 'private-' not in result.headers['location']
    client.cookies.set('studio_oauth_'+provider, state)
    assert client.get(callback, params={'state':state,'code':'test-code'}).status_code == 400
    assert client.get('/api/accounts/connections').status_code == 401
    response = client.get('/api/accounts/connections', headers=HEADERS)
    accounts = response.json()
    assert len(accounts) == 1 and accounts[0]['influencer_id'] == owner
    assert accounts[0]['publishing_available'] is False
    assert 'private-access' not in response.text and 'encrypted_tokens' not in response.text
    with Session(engine) as session:
        stored = session.get(oauth.LinkedAccount, accounts[0]['id'])
        assert 'private-access' not in stored.encrypted_tokens
        assert json.loads(Fernet(key.encode()).decrypt(stored.encrypted_tokens.encode()))['refresh_token'] == 'private-refresh'
    client.cookies.clear()  # Remove the deliberately injected replay-test cookie.
    state, _, _ = start(client, other, provider)
    result = client.get(callback, params={'state':state,'code':'test-code'}, follow_redirects=False)
    assert result.headers['location'].endswith('result=account_already_linked')
    url = f"/api/accounts/connections/{accounts[0]['id']}"
    assert client.delete(url).status_code == 401
    assert client.delete(url, headers=HEADERS).status_code == 204
    assert client.get('/api/accounts/connections', headers=HEADERS).json() == []


@pytest.mark.parametrize('provider', ['google','tiktok','snapchat'])
def test_exchange_requests(client, monkeypatch, provider):
    requests = []
    def handler(request):
        requests.append(request)
        if str(request.url) == oauth.PROVIDERS[provider]['token']:
            body = parse_qs(request.content.decode())
            assert body['code_verifier'] == ['verifier']
            assert body['grant_type'] == ['authorization_code']
            if provider == 'snapchat':
                assert request.headers['authorization'].startswith('Basic ')
            else:
                assert body['client_key' if provider == 'tiktok' else 'client_id'] == ['test-id']
            return httpx.Response(200, json={'access_token':'access','refresh_token':'refresh','expires_in':3600,'open_id':'123'})
        assert request.headers['Authorization'] == 'Bearer access'
        if provider == 'google':
            assert request.url.host == 'openidconnect.googleapis.com'
            data = {'sub':'123','email':'demo@example.com'}
        elif provider == 'tiktok':
            assert request.url.host == 'open.tiktokapis.com'
            data = {'data':{'user':{'open_id':'123','display_name':'Demo'}}}
        else:
            assert request.url.host == 'kit.snapchat.com' and request.method == 'POST'
            assert json.loads(request.content)['query'] == '{me{externalId displayName}}'
            data = {'data':{'me':{'externalId':'123','displayName':'Demo'}}}
        return httpx.Response(200, json=data)
    real = httpx.AsyncClient
    monkeypatch.setattr(oauth.httpx, 'AsyncClient', lambda **kwargs: real(transport=httpx.MockTransport(handler), **kwargs))
    _, config = oauth.provider_config(provider)
    account, name, tokens, expiry, scopes = asyncio.run(oauth.exchange(provider, config, 'code', 'verifier'))
    assert account == '123' and tokens['refresh_token'] == 'refresh'
    assert expiry > time.time() and len(requests) == 2


def test_google_localhost_and_missing_configuration(client, monkeypatch):
    client, _, _ = client
    monkeypatch.setenv('GOOGLE_REDIRECT_URI', 'http://localhost:5173/api/integrations/google/callback')
    monkeypatch.setenv('STUDIO_FRONTEND_URL', 'http://localhost:5173')
    _, config = oauth.provider_config('google')
    assert config['secure'] is False
    owner = create(client)
    _, _, response = start(client, owner, 'google')
    assert 'Secure' not in response.headers['set-cookie']
    monkeypatch.setenv('STUDIO_FRONTEND_URL', 'http://different-host.test')
    assert client.post(f'/api/influencers/{owner}/connections/google/connect', headers=HEADERS).status_code == 503
    monkeypatch.delenv('TIKTOK_CLIENT_ID')
    statuses = client.get('/api/integrations/oauth/setup').json()
    assert next(p for p in statuses if p['provider']=='tiktok')['configured'] is False
    assert client.post(f'/api/influencers/{owner}/connections/unsupported/connect', headers=HEADERS).status_code == 404


def test_cancelled_expired_and_cross_provider_state(client):
    client, engine, _ = client
    owner = create(client)
    state, _, _ = start(client, owner, 'google')
    client.cookies.set('studio_oauth_tiktok', state)
    assert client.get('/api/integrations/tiktok/callback', params={'state':state,'code':'code'}).status_code == 400
    response = client.get('/api/integrations/google/callback', params={'state':state,'error':'access_denied'}, follow_redirects=False)
    assert response.headers['location'].endswith('result=cancelled')
    state, _, _ = start(client, owner, 'google')
    with Session(engine) as session:
        session.get(oauth.LinkAttempt, oauth.digest(state)).expires_at = 0
        session.commit()
    assert client.get('/api/integrations/google/callback', params={'state':state,'code':'code'}).status_code == 400


def test_delete_influencer_cleans_tokens_and_pending_attempts(client):
    client, engine, _ = client
    owner = create(client)
    start(client, owner, 'google')
    with Session(engine) as session:
        session.add(oauth.LinkedAccount(influencer_id=owner, provider='google',account_id='123',display_name='Demo',encrypted_tokens='encrypted',expires_at=9999999999,scopes='identity'))
        session.commit()
    assert client.delete(f'/api/influencers/{owner}').status_code == 401
    assert client.delete(f'/api/influencers/{owner}', headers=HEADERS).status_code == 204
    with Session(engine) as session:
        assert list(session.scalars(select(oauth.LinkedAccount))) == []
        assert list(session.scalars(select(oauth.LinkAttempt))) == []


def test_setup_identifies_specific_local_configuration_error(client, monkeypatch):
    client, _, _ = client
    def google_status():
        return next(item for item in client.get('/api/integrations/oauth/setup').json() if item['provider']=='google')
    monkeypatch.setenv('GOOGLE_REDIRECT_URI', 'http://localhost:5173/api/integrations/google/callback')
    # Copying an HTTPS placeholder frontend URL must explain the exact mismatch.
    monkeypatch.setenv('STUDIO_FRONTEND_URL', 'https://your-studio.example')
    result = google_status()
    assert result['configured'] is False
    assert 'same scheme, hostname, and port' in result['message']
    assert 'test-secret' not in result['message']
    monkeypatch.setenv('STUDIO_FRONTEND_URL', 'http://localhost:5173')
    assert google_status()['configured'] is True
    monkeypatch.setenv('GOOGLE_REDIRECT_URI', 'http://localhost:5173/wrong-path')
    assert 'must end in /api/integrations/google/callback' in google_status()['message']
    monkeypatch.setenv('GOOGLE_REDIRECT_URI', 'http://localhost:5173/api/integrations/google/callback')
    monkeypatch.setenv('TOKEN_ENCRYPTION_KEY', 'not-a-real-key')
    assert 'TOKEN_ENCRYPTION_KEY is not a valid' in google_status()['message']
    assert 'not-a-real-key' not in google_status()['message']
