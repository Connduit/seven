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
