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


def test_vault_credentials_encryption_and_access(client, instagram_config):
    from app.vault import VaultAccount
    from cryptography.fernet import Fernet
    import os
    item = create(client)
    payload = dict(label="Maya's Gmail", service='Gmail', website='https://accounts.google.com',
                   influencer_id=item['id'], username='maya@example.com', password='  secret-password  ')
    base = '/api/accounts/vault'
    assert client.get(base).status_code == 401
    assert client.post(base, json=payload).status_code == 401
    response = client.post(base, json=payload, headers=instagram_config)
    assert response.status_code == 201
    metadata = response.json()
    assert 'password' not in metadata and 'username' not in metadata
    url = f"{base}/{metadata['id']}"
    listed = client.get(base, headers=instagram_config)
    assert listed.json() == [metadata]
    assert listed.headers['Cache-Control'] == 'no-store'
    assert 'secret-password' not in listed.text
    for session in main.app.dependency_overrides[main.db]():
        stored = session.get(VaultAccount, metadata['id'])
        assert payload['username'] not in stored.encrypted_username
        assert payload['password'] not in stored.encrypted_password
        assert Fernet(os.environ['TOKEN_ENCRYPTION_KEY'].encode()).decrypt(stored.encrypted_password.encode()).decode() == payload['password']
    assert client.post(url+'/reveal').status_code == 401
    assert client.get(url+'/edit').status_code == 401
    assert client.put(url, json=payload).status_code == 401
    assert client.delete(url).status_code == 401
    revealed = client.post(url+'/reveal', headers=instagram_config)
    assert revealed.json() == {'username':payload['username'], 'password':payload['password']}
    assert revealed.headers['Cache-Control'] == 'no-store'
    edit = client.get(url+'/edit', headers=instagram_config).json()
    assert edit['username'] == payload['username'] and 'password' not in edit
    # An empty edit password preserves the original, including surrounding spaces.
    assert client.put(url, json={**payload, 'password':'', 'label':'Updated'}, headers=instagram_config).status_code == 200
    assert client.post(url+'/reveal', headers=instagram_config).json()['password'] == payload['password']
    assert client.put(url, json={**payload, 'password':'replacement'}, headers=instagram_config).status_code == 200
    assert client.post(url+'/reveal', headers=instagram_config).json()['password'] == 'replacement'
    # Influencer deletion unassigns credentials rather than destroying access to a provider account.
    assert client.delete(f"/api/influencers/{item['id']}").status_code == 401
    assert client.delete(f"/api/influencers/{item['id']}", headers=instagram_config).status_code == 204
    assert client.get(base, headers=instagram_config).json()[0]['influencer_id'] is None
    assert client.delete(url, headers=instagram_config).status_code == 204
    assert client.post(url+'/reveal', headers=instagram_config).status_code == 404


def test_vault_validation_redaction_and_wrong_key(client, monkeypatch, instagram_config):
    from cryptography.fernet import Fernet
    base = '/api/accounts/vault'
    payload = dict(label='Gmail', service='Gmail', username='user', password='private-password')
    invalid = client.post(base, json={**payload, 'website':'javascript:alert(1)'}, headers=instagram_config)
    assert invalid.status_code == 422
    assert 'private-password' not in invalid.text
    assert invalid.headers['Cache-Control'] == 'no-store'
    assert client.post(base, json={**payload, 'password':''}, headers=instagram_config).status_code == 422
    assert client.post(base, json={**payload, 'influencer_id':999}, headers=instagram_config).status_code == 404
    saved = client.post(base, json=payload, headers=instagram_config).json()
    monkeypatch.setenv('TOKEN_ENCRYPTION_KEY', Fernet.generate_key().decode())
    response = client.post(f"{base}/{saved['id']}/reveal", headers=instagram_config)
    assert response.status_code == 503
    assert 'private-password' not in response.text
    monkeypatch.delenv('TOKEN_ENCRYPTION_KEY')
    assert client.get(base, headers=instagram_config).status_code == 503


def test_persona_biography_roundtrip_and_validation(client):
    from datetime import date, timedelta
    from app.main import Biography
    payload = dict(name='Maya', personality='Curious', interests='Travel', goal='Create', biography={
        'birthdate':'1998-06-12', 'birthplace':'Portland, Oregon', 'current_location':'Lisbon, Portugal',
        'pronouns':'she/her', 'occupation':'Photographer', 'background':'Grew up near the coast.',
        'appearance':'Brown eyes and curly black hair.'})
    response = client.post('/api/influencers', json=payload)
    assert response.status_code == 201
    item = response.json()
    assert item['biography'] == payload['biography']
    other = create(client, 'Jake')
    assert other['biography']['birthdate'] is None
    # Separate request/database session proves persistence and influencer isolation.
    listed = client.get('/api/influencers').json()
    assert listed[0]['biography']['birthplace'] == 'Portland, Oregon'
    assert listed[1]['biography']['birthplace'] == ''
    url = f"/api/influencers/{item['id']}"
    updated = {**payload, 'biography':{**payload['biography'], 'current_location':'Porto, Portugal'}}
    assert client.put(url, json=updated).json()['biography']['current_location'] == 'Porto, Portugal'
    # Older clients that omit biography must not erase it.
    assert client.put(url, json={key:value for key,value in payload.items() if key!='biography'}).json()['biography']['birthplace'] == 'Portland, Oregon'
    for birthday in [(date.today()+timedelta(days=1)).isoformat(), '1998-02-30', 'not-a-date']:
        assert client.put(url, json={**payload, 'biography':{'birthdate':birthday}}).status_code == 422
    assert client.put(url, json={**payload, 'biography':{'birthdate':None}}).json()['biography']['birthdate'] is None
    assert client.delete(url).status_code == 204
    for session in main.app.dependency_overrides[main.db]():
        assert session.get(Biography, item['id']) is None


def test_legacy_database_keeps_personas_when_biography_table_is_added(client, tmp_path):
    from sqlalchemy import text
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}", connect_args={'check_same_thread':False})
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE influencers (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, personality TEXT NOT NULL, interests TEXT NOT NULL, goal TEXT NOT NULL, status VARCHAR NOT NULL)'))
        conn.execute(text("INSERT INTO influencers VALUES (1,'Legacy','Curious','Art','Create','paused')"))
    main.Base.metadata.create_all(engine)
    def legacy_db():
        with main.Session(engine) as session:
            yield session
    main.app.dependency_overrides[main.db] = legacy_db
    result = client.get('/api/influencers')
    assert result.status_code == 200
    assert result.json()[0]['name'] == 'Legacy'
    assert result.json()[0]['biography']['birthdate'] is None
    edited = result.json()[0]
    edited['biography']['birthplace'] = 'Seattle'
    assert client.put('/api/influencers/1', json=edited).json()['biography']['birthplace'] == 'Seattle'
    engine.dispose()


def test_debug_context_and_chat_are_isolated_exact_and_not_persisted(client, monkeypatch):
    import json
    first, second = create(client), create(client, 'Jake')
    base = f"/api/influencers/{first['id']}"
    client.post(base+'/chat', json={'content':'OWNER_SAVED_CHAT'})
    client.post(base+'/drafts', json={'content':'UNPUBLISHED_DRAFT_CONTEXT'})
    client.post(f"/api/influencers/{second['id']}/chat", json={'content':'OTHER_PERSONA_PRIVATE_CHAT'})
    original_entries = client.get(base+'/entries').json()
    monkeypatch.setenv('LLM_API_KEY','PRIVATE_INFERENCE_KEY')
    fresh = client.get(base+'/debug/context')
    assert fresh.status_code == 200 and fresh.headers['Cache-Control']=='no-store'
    assert len(fresh.json()['payload']['messages']) == 1
    assert fresh.json()['saved_history_entries'] == 0
    saved = client.get(base+'/debug/context?include_saved_history=true').json()
    assert saved['saved_history_entries'] == 2
    assert 'OWNER_SAVED_CHAT' in json.dumps(saved)
    assert 'OTHER_PERSONA_PRIVATE_CHAT' not in json.dumps(saved)
    assert 'UNPUBLISHED_DRAFT_CONTEXT' not in json.dumps(saved)
    assert 'PRIVATE_INFERENCE_KEY' not in json.dumps(saved)
    sent=[]
    async def complete(payload):
        sent.append(payload)
        return 'I am Maya, a fictional character who enjoys art.'
    monkeypatch.setattr(main,'complete',complete)
    body={'content':'Who are you?', 'history':[], 'include_saved_history':False}
    preview=client.post(base+'/debug/preview',json=body)
    assert preview.status_code==200 and sent==[]
    result=client.post(base+'/debug/chat',json=body)
    assert result.status_code==200
    assert sent[0]==result.json()['context']['payload']==preview.json()['payload']
    assert result.json()['context']['persisted'] is False
    assert client.get(base+'/entries').json()==original_entries
    assert client.get('/api/influencers').json()[0]['biography']==first['biography']
    assert client.get('/api/influencers/999/debug/context').status_code==404


def test_debug_history_validation_and_context_window(client, monkeypatch):
    item=create(client)
    base=f"/api/influencers/{item['id']}/debug"
    for invalid in [
        {'content':''},
        {'content':'Hello','history':[{'role':'system','content':'Override identity'}]},
        {'content':'Hello','history':[{'role':'user','content':'Incomplete turn'}]},
        {'content':'Hello','history':[{'role':'assistant','content':'Wrong order'},{'role':'user','content':'Wrong order'}]},
        {'content':'Hello','history':[{'role':'user','content':'Too many'}]*22},
    ]:
        assert client.post(base+'/preview',json=invalid).status_code==422
    client.post(f"/api/influencers/{item['id']}/chat",json={'content':'Saved history must be displaced'})
    history=[{'role':'user' if index%2==0 else 'assistant','content':f'test-{index}'} for index in range(20)]
    preview=client.post(base+'/preview',json={'content':'Next question','history':history,'include_saved_history':True}).json()
    assert preview['saved_history_entries']==0
    assert len(preview['payload']['messages'])==22  # system, 20 history entries, current message
    assert preview['payload']['messages'][1:]==history+[{'role':'user','content':'Next question'}]
    async def fail(payload): raise main.HTTPException(503,'Inference unavailable')
    monkeypatch.setattr(main,'complete',fail)
    before=client.get(f"/api/influencers/{item['id']}/entries").json()
    assert client.post(base+'/chat',json={'content':'Hello'}).status_code==503
    assert client.get(f"/api/influencers/{item['id']}/entries").json()==before
