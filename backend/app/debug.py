"""Non-persistent persona testing using the same inference path as creator chat."""
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from . import main

router = APIRouter(prefix='/api/influencers')


class TestMessage(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=10000)


class DebugInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    content: str = Field(min_length=1, max_length=10000)
    history: list[TestMessage] = Field(default_factory=list, max_length=20)
    include_saved_history: bool = False

    @model_validator(mode='after')
    def valid_history(self):
        if len(self.history) % 2 or any(message.role != ('user' if index % 2 == 0 else 'assistant') for index, message in enumerate(self.history)):
            raise ValueError('Test history must contain complete alternating user/assistant turns.')
        return self


def context(session, influencer_id, include_saved_history, test_history=None, content=None):
    item = main.find(session, influencer_id)
    saved = main.history(session, influencer_id, 'chat')[-20:] if include_saved_history else []
    test_history = test_history or []
    messages = ([{'role': entry.role, 'content': entry.content} for entry in saved] + test_history)[-20:]
    saved_used = min(len(saved), max(0, 20-len(test_history)))
    if content is not None:
        messages.append({'role':'user', 'content':content})
    return {
        'profile': main.InfluencerOutput.model_validate(item).model_dump(mode='json'),
        'payload': main.inference_payload(item, messages),
        'saved_history_entries': saved_used,
        'include_saved_history': include_saved_history,
        'persisted': False,
    }


@router.get('/{influencer_id}/debug/context')
def inspect(influencer_id: int, response: Response, include_saved_history: bool = False, session: Session = Depends(main.db)):
    response.headers['Cache-Control'] = 'no-store'
    return context(session, influencer_id, include_saved_history)


@router.post('/{influencer_id}/debug/preview')
def preview(influencer_id: int, payload: DebugInput, response: Response, session: Session = Depends(main.db)):
    response.headers['Cache-Control'] = 'no-store'
    return context(session, influencer_id, payload.include_saved_history,
                   [entry.model_dump() for entry in payload.history], payload.content)


@router.post('/{influencer_id}/debug/chat')
async def chat(influencer_id: int, payload: DebugInput, response: Response, session: Session = Depends(main.db)):
    snapshot = context(session, influencer_id, payload.include_saved_history,
                       [entry.model_dump() for entry in payload.history], payload.content)
    # Use this exact snapshot for the request and inspector. Never write Entry or Biography rows.
    reply = await main.complete(snapshot['payload'])
    response.headers['Cache-Control'] = 'no-store'
    return {'reply':reply, 'context':snapshot}
