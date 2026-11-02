"""Configuration for the existing instance-wide embedding index."""
import os
from backend.db.database import SessionLocal
from backend.db.models import EmbeddingSettings
from backend.schemas.settings import EmbeddingSettingsResponse, EmbeddingSettingsUpdate
from backend.vector.embedding import DEFAULT_LOCAL_MODEL, DEFAULT_REMOTE_MODEL


def saved_settings(db=None):
    if db is None:
        with SessionLocal() as session:
            return saved_settings(session)
    row = db.get(EmbeddingSettings, 1)
    return ({name: getattr(row, name) for name in ('provider', 'api_key', 'base_url', 'model')}
            if row is not None else None)


def resolve_settings(db=None):
    saved = saved_settings(db)
    if saved is not None:
        return saved
    provider = (os.getenv('EMBEDDING_PROVIDER') or 'openai').lower()
    return dict(provider=provider, api_key=os.getenv('EMBEDDING_API_KEY') or os.getenv('OPENAI_API_KEY') or '',
        base_url=os.getenv('EMBEDDING_BASE_URL') or os.getenv('OPENAI_BASE_URL') or '',
        model=os.getenv('EMBEDDING_MODEL') or (DEFAULT_LOCAL_MODEL if provider == 'local' else DEFAULT_REMOTE_MODEL))


def read_settings(db):
    settings = resolve_settings(db)
    key = settings.pop('api_key')
    return EmbeddingSettingsResponse(**settings, api_key=key, has_api_key=bool(key), api_key_hint=key[-4:] if key else '',
        source='saved' if saved_settings(db) is not None else 'environment')


def save_settings(payload: EmbeddingSettingsUpdate, db):
    values = resolve_settings(db)
    for name in ('provider', 'base_url', 'model'):
        if getattr(payload, name) is not None:
            values[name] = getattr(payload, name)
    if payload.clear_api_key:
        values['api_key'] = ''
    elif payload.api_key:
        values['api_key'] = payload.api_key
    row = db.get(EmbeddingSettings, 1)
    if row is None:
        row = EmbeddingSettings(id=1, **values)
        db.add(row)
    else:
        for name, value in values.items():
            setattr(row, name, value)
    db.commit()
    return read_settings(db)
