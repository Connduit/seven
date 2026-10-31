import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import main


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    main.Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    def override():
        with factory() as session:
            yield session
    main.app.dependency_overrides[main.db] = override
    async def generate(item, messages):
        return f"{item.name}: {messages[-1]['content']}"
    monkeypatch.setattr(main, "generate", generate)
    with TestClient(main.app) as client:
        yield client
    main.app.dependency_overrides.clear()


def create(client, name="Maya"):
    response = client.post('/api/influencers', json=dict(name=name, personality="Curious", interests="Art", goal="Create"))
    assert response.status_code == 201
    return response.json()


def test_management(client):
    item = create(client)
    assert client.get('/api/influencers').json() == [item]
    item['status'] = 'archived'
    assert client.put(f"/api/influencers/{item['id']}", json=item).json()['status'] == 'archived'
    assert client.post('/api/influencers', json={}).status_code == 422
    assert client.get('/api/influencers/999/entries').status_code == 404


def test_isolation_and_drafts(client):
    first, second = create(client), create(client, "Jake")
    url = f"/api/influencers/{first['id']}"
    assert client.post(url+'/chat', json={'content':'Hello'}).status_code == 200
    assert client.post(url+'/drafts', json={'content':'Introduce yourself'}).status_code == 201
    entries = client.get(url+'/entries').json()
    assert [e['kind'] for e in entries] == ['chat','chat','draft']
    assert client.get(f"/api/influencers/{second['id']}/entries").json() == []


def test_inference_failure_is_atomic(client, monkeypatch):
    async def fail(*args):
        raise main.HTTPException(503, 'Inference unavailable')
    monkeypatch.setattr(main, 'generate', fail)
    item = create(client)
    url = f"/api/influencers/{item['id']}"
    assert client.post(url+'/chat', json={'content':'Hello'}).status_code == 503
    assert client.get(url+'/entries').json() == []


def test_social_pages_are_persisted_and_isolated(client):
    first, second = create(client), create(client, 'Jake')
    url = f"/api/influencers/{first['id']}/social-pages"
    payload = {'platform': 'Instagram', 'url': 'https://www.instagram.com/maya/'}
    result = client.post(url, json=payload)
    assert result.status_code == 201
    page = result.json()
    assert client.get(url).json() == [page]
    other = f"/api/influencers/{second['id']}/social-pages"
    assert client.get(other).json() == []
    assert client.delete(other + f"/{page['id']}").status_code == 404
    for bad in ['javascript:alert(1)', 'https://instagram.com.evil.test/maya', 'http://instagram.com/maya', 'https://instagram.com']:
        assert client.post(url, json={**payload, 'url': bad}).status_code == 422
    assert client.delete(url + f"/{page['id']}").status_code == 204
    assert client.get(url).json() == []
    assert client.get('/api/influencers/999/social-pages').status_code == 404


def test_tile_status_and_deletion(client):
    item, survivor = create(client), create(client, 'Jake')
    url = f"/api/influencers/{item['id']}"
    for status in ['active', 'paused', 'archived', 'paused']:
        result = client.patch(url+'/status', json={'status':status})
        assert result.status_code == 200
        assert result.json()['status'] == status
        assert result.json()['personality'] == item['personality']
    assert client.patch(url+'/status', json={'status':'invalid'}).status_code == 422
    client.post(url+'/chat', json={'content':'Hello'})
    client.post(url+'/drafts', json={'content':'Hello'})
    client.post(url+'/social-pages', json={'platform':'X','url':'https://x.com/maya'})
    assert client.delete(url).status_code == 204
    assert client.delete(url).status_code == 404
    assert client.get('/api/influencers').json() == [survivor]
    # Check actual child rows, not just endpoints that reject the missing parent.
    with next(main.app.dependency_overrides[main.db]()) as session:
        assert list(session.scalars(main.select(main.Entry))) == []
        assert list(session.scalars(main.select(main.SocialPage))) == []


@pytest.fixture
def instagram_config(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv('INSTAGRAM_APP_ID', 'test-app')
    monkeypatch.setenv('INSTAGRAM_APP_SECRET', 'test-secret')
    monkeypatch.setenv('INSTAGRAM_REDIRECT_URI', 'https://testserver/api/integrations/instagram/callback')
    monkeypatch.setenv('STUDIO_FRONTEND_URL', 'https://testserver')
    monkeypatch.setenv('TOKEN_ENCRYPTION_KEY', Fernet.generate_key().decode())
    monkeypatch.setenv('STUDIO_ADMIN_KEY', 'test-admin-key-with-at-least-32-characters')
    return {'X-Studio-Key': 'test-admin-key-with-at-least-32-characters'}


def test_instagram_oauth_and_permissions(client, monkeypatch, instagram_config):
    import os
    import time
    import httpx
    from urllib.parse import urlsplit, parse_qs
    from cryptography.fernet import Fernet
    from app import instagram
    client.base_url = httpx.URL('https://testserver')
    first, other = create(client), create(client, 'Jake')
    base = f"/api/influencers/{first['id']}/instagram"
    assert client.post(base+'/connect').status_code == 401
    result = client.post(base+'/connect', headers=instagram_config)
    assert result.status_code == 200
    assert 'HttpOnly' in result.headers['set-cookie']
    assert 'Secure' in result.headers['set-cookie']
    state = parse_qs(urlsplit(result.json()['authorization_url']).query)['state'][0]
    async def exchange(code):
        assert code == 'test-code'
        return '12345', 'maya', 'private-access-token', int(time.time()) + 3600
    monkeypatch.setattr(instagram, 'exchange', exchange)
    callback = '/api/integrations/instagram/callback'
    assert client.get(callback, params={'state':'wrong', 'code':'test-code'}).status_code == 400
    result = client.get(callback, params={'state':state, 'code':'test-code'}, follow_redirects=False)
    assert result.status_code == 303
    assert result.headers['location'] == 'https://testserver/?instagram=connected'
    client.cookies.set(instagram.COOKIE, state)
    assert client.get(callback, params={'state':state, 'code':'test-code'}).status_code == 400
    accounts = client.get(base, headers=instagram_config).json()
    assert len(accounts) == 1
    assert 'private-access-token' not in str(accounts)
    account = accounts[0]
    assert account['publishing_policy'] == 'disabled'
    assert account['publishing_available'] is False
    for session in main.app.dependency_overrides[main.db]():
        stored = session.get(instagram.InstagramConnection, account['id'])
        assert stored.encrypted_token != 'private-access-token'
        assert Fernet(os.environ['TOKEN_ENCRYPTION_KEY'].encode()).decrypt(stored.encrypted_token.encode()) == b'private-access-token'
    assert client.get(f"/api/influencers/{other['id']}/instagram", headers=instagram_config).json() == []
    assert client.patch(base+f"/{account['id']}", json={'publishing_policy':'autonomous','daily_post_limit':1}, headers=instagram_config).status_code == 422
    assert client.patch(base+f"/{account['id']}", json={'publishing_policy':'approval_required','daily_post_limit':0}, headers=instagram_config).status_code == 422
    result = client.patch(base+f"/{account['id']}", json={'publishing_policy':'approval_required','daily_post_limit':2}, headers=instagram_config)
    assert result.json()['daily_post_limit'] == 2
    assert client.delete(f"/api/influencers/{other['id']}/instagram/{account['id']}", headers=instagram_config).status_code == 404
    assert client.delete(f"/api/influencers/{first['id']}").status_code == 401
    assert client.delete(base+f"/{account['id']}", headers=instagram_config).status_code == 204
    assert client.get(base, headers=instagram_config).json() == []


def test_instagram_configuration_missing(client, monkeypatch):
    monkeypatch.delenv('INSTAGRAM_APP_ID', raising=False)
    assert client.get('/api/integrations/instagram/setup').json()['configured'] is False


def test_instagram_expired_state_and_provider_failure(client, monkeypatch, instagram_config):
    import httpx
    import time
    from app import instagram
    from urllib.parse import urlsplit, parse_qs
    client.base_url = httpx.URL('https://testserver')
    item = create(client)
    base = f"/api/influencers/{item['id']}/instagram"
    def start():
        response = client.post(base+'/connect', headers=instagram_config)
        return parse_qs(urlsplit(response.json()['authorization_url']).query)['state'][0]
    state = start()
    for session in main.app.dependency_overrides[main.db]():
        attempt = session.get(instagram.OAuthAttempt, instagram.digest(state))
        attempt.expires_at = int(time.time()) - 1
        session.commit()
    callback = '/api/integrations/instagram/callback'
    assert client.get(callback, params={'state':state,'code':'code'}).status_code == 400
    state = start()
    async def fail(code):
        raise httpx.ConnectError('provider unavailable')
    monkeypatch.setattr(instagram, 'exchange', fail)
    response = client.get(callback, params={'state':state,'code':'code'}, follow_redirects=False)
    assert response.headers['location'].endswith('instagram=failed')
    assert client.get(base, headers=instagram_config).json() == []


def test_instagram_exchange_protocol(monkeypatch, instagram_config):
    import asyncio
    import httpx
    from app import instagram
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.host == 'api.instagram.com':
            assert request.method == 'POST'
            assert b'grant_type=authorization_code' in request.content
            return httpx.Response(200, json={'access_token':'short-token'})
        if request.url.path == '/access_token':
            assert request.url.params['grant_type'] == 'ig_exchange_token'
            assert request.url.params['access_token'] == 'short-token'
            return httpx.Response(200, json={'access_token':'long-token','expires_in':3600})
        assert request.headers['Authorization'] == 'Bearer long-token'
        return httpx.Response(200, json={'user_id':'123','username':'maya'})
    real_client = httpx.AsyncClient
    monkeypatch.setattr(instagram.httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    account_id, username, token, expiry = asyncio.run(instagram.exchange('code'))
    assert (account_id, username, token) == ('123','maya','long-token')
    assert len(calls) == 3
