"""Exercise the real inference client without a local model or external calls."""
import asyncio
from types import SimpleNamespace

import httpx
import pytest

from app import main


def test_character_context_sent_to_shared_model_without_cross_persona_leaks(monkeypatch):
    requests = []
    def handler(request):
        import json
        payload = json.loads(request.content)
        requests.append(payload)
        return httpx.Response(200, json={'choices': [{'message': {'content': 'A quiet beach sounds like my kind of weekend.'}}]})
    real_client = httpx.AsyncClient
    monkeypatch.setattr(main.httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    maya = SimpleNamespace(name='Maya', personality='Thoughtful', interests='Art', goal='Create', biography={'birthdate':'1998-06-12','birthplace':'Portland','background':'Grew up near the coast.'})
    jake = SimpleNamespace(name='Jake', personality='Competitive', interests='Cars', goal='Build community')
    messages = [{'role':'user', 'content':'What would you like to do this weekend?'}]
    assert asyncio.run(main.generate(maya, messages)) == 'A quiet beach sounds like my kind of weekend.'
    asyncio.run(main.generate(jake, messages))
    assert requests[0]['messages'][0]['role'] == 'system'
    first = requests[0]['messages'][0]['content']
    second = requests[1]['messages'][0]['content']
    assert '"name": "Maya"' in first and '"name": "Jake"' not in first
    assert '"name": "Jake"' in second and '"name": "Maya"' not in second
    assert '"birthdate": "1998-06-12"' in first
    assert '"birthplace": "Portland"' in first
    assert '"birthplace": "Portland"' not in second
    assert requests[0]['messages'][1:] == messages
    assert messages == [{'role':'user', 'content':'What would you like to do this weekend?'}]
    # Identity transparency and draft/action boundaries must travel with every persona request.
    for prompt in [first, second]:
        assert 'Speak naturally in first person' in prompt
        assert 'answer truthfully' in prompt
        assert 'requires creator review' in prompt
        assert 'Do not claim that generating a draft means a trip occurred' in prompt


def test_empty_model_response_reports_unavailable(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={'choices':[{'message':{'content':'   '}}]})
    real_client = httpx.AsyncClient
    monkeypatch.setattr(main.httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    item = SimpleNamespace(name='Maya', personality='Curious', interests='Art', goal='Create')
    with pytest.raises(main.HTTPException) as exc:
        asyncio.run(main.generate(item, [{'role':'user', 'content':'Hello'}]))
    assert exc.value.status_code == 503
