"""Administrator-only credential vault for a trusted single-user studio."""
import os
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, SecretStr, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .main import Base, db, find
from .instagram import InstagramConnection, admin, public

router = APIRouter(prefix='/api/accounts', dependencies=[Depends(admin)])


class VaultAccount(Base):
    __tablename__ = 'vault_accounts'
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str]
    service: Mapped[str]
    website: Mapped[str] = mapped_column(default='')
    influencer_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    encrypted_username: Mapped[str]
    encrypted_password: Mapped[str]


def cipher():
    try:
        return Fernet(os.environ['TOKEN_ENCRYPTION_KEY'].encode())
    except (KeyError, ValueError, TypeError):
        raise HTTPException(503, 'Set a valid TOKEN_ENCRYPTION_KEY before using the credential vault.')


def metadata(item):
    return {'id': item.id, 'label': item.label, 'service': item.service, 'website': item.website,
            'influencer_id': item.influencer_id}


def owned(session, account_id):
    item = session.get(VaultAccount, account_id)
    if not item:
        raise HTTPException(404, 'Saved account not found')
    return item


class AccountInput(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    service: str = Field(min_length=1, max_length=100)
    website: str = Field(default='', max_length=2048)
    influencer_id: int | None = None
    username: SecretStr = Field(min_length=1, max_length=1000)
    # Empty on update preserves the existing password. Creation requires a password.
    password: SecretStr = Field(default=SecretStr(''), max_length=10000)

    @field_validator('label', 'service')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Cannot be blank')
        return value.strip()

    @field_validator('website')
    @classmethod
    def valid_website(cls, value):
        if not value:
            return ''
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Use an HTTPS website URL')
        return value


@router.get('/vault')
def list_accounts(response: Response, session: Session = Depends(db)):
    cipher()
    response.headers['Cache-Control'] = 'no-store'
    return [metadata(item) for item in session.scalars(select(VaultAccount).order_by(VaultAccount.id))]


@router.post('/vault', status_code=201)
def add(payload: AccountInput, response: Response, session: Session = Depends(db)):
    encryption = cipher()
    if not payload.password.get_secret_value():
        raise HTTPException(422, 'Enter a password to create a saved account.')
    if payload.influencer_id is not None:
        find(session, payload.influencer_id)
    item = VaultAccount(label=payload.label, service=payload.service, website=payload.website,
                        influencer_id=payload.influencer_id,
                        encrypted_username=encryption.encrypt(payload.username.get_secret_value().encode()).decode(),
                        encrypted_password=encryption.encrypt(payload.password.get_secret_value().encode()).decode())
    session.add(item)
    session.commit()
    session.refresh(item)
    response.headers['Cache-Control'] = 'no-store'
    return metadata(item)


@router.put('/vault/{account_id}')
def edit(account_id: int, payload: AccountInput, response: Response, session: Session = Depends(db)):
    encryption = cipher()
    item = owned(session, account_id)
    if payload.influencer_id is not None:
        find(session, payload.influencer_id)
    item.label, item.service, item.website, item.influencer_id = payload.label, payload.service, payload.website, payload.influencer_id
    item.encrypted_username = encryption.encrypt(payload.username.get_secret_value().encode()).decode()
    if payload.password.get_secret_value():
        item.encrypted_password = encryption.encrypt(payload.password.get_secret_value().encode()).decode()
    session.commit()
    response.headers['Cache-Control'] = 'no-store'
    return metadata(item)


@router.post('/vault/{account_id}/reveal')
def reveal(account_id: int, response: Response, session: Session = Depends(db)):
    encryption = cipher()
    item = owned(session, account_id)
    try:
        username = encryption.decrypt(item.encrypted_username.encode()).decode()
        password = encryption.decrypt(item.encrypted_password.encode()).decode()
    except (InvalidToken, UnicodeError):
        raise HTTPException(503, 'Cannot decrypt this account. Restore the original encryption key from your backup.')
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Pragma'] = 'no-cache'
    return {'username': username, 'password': password}


@router.delete('/vault/{account_id}', status_code=204)
def remove(account_id: int, session: Session = Depends(db)):
    session.delete(owned(session, account_id))
    session.commit()


@router.get('/instagram')
def all_instagram(response: Response, session: Session = Depends(db)):
    response.headers['Cache-Control'] = 'no-store'
    return [{**public(item), 'influencer_id': item.influencer_id} for item in session.scalars(select(InstagramConnection).order_by(InstagramConnection.id))]


@router.get('/vault/{account_id}/edit')
def edit_details(account_id: int, response: Response, session: Session = Depends(db)):
    item = owned(session, account_id)
    try:
        username = cipher().decrypt(item.encrypted_username.encode()).decode()
    except (InvalidToken, UnicodeError):
        raise HTTPException(503, 'Cannot decrypt this account. Restore the original encryption key from your backup.')
    response.headers['Cache-Control'] = 'no-store'
    return {**metadata(item), 'username': username}
