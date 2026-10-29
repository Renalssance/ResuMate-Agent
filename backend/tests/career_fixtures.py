"""Disposable databases for T02; never connect to application data."""
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from backend.db.database import Base, build_engine
from backend.db.models import User, Resume, JobDescription
from backend.db import agent_models, career_models  # register all tables


@pytest.fixture(params=['sqlite', 'mysql'])
def career_engine(request, tmp_path):
    if request.param == 'sqlite':
        engine = build_engine(f"sqlite:///{tmp_path / 'career.db'}")
        yield engine
        engine.dispose()
        return
    socket = os.getenv('RESUMATE_TEST_MYSQL_SOCKET')
    if not socket:
        pytest.skip('Set RESUMATE_TEST_MYSQL_SOCKET for disposable MySQL tests')
    name = 'resumate_test_' + uuid4().hex
    url = URL.create('mysql+pymysql', username='root', query={'unix_socket': socket, 'charset': 'utf8mb4'})
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4'))
    engine = create_engine(url.set(database=name))
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP DATABASE `{name}`'))
        admin.dispose()


@pytest.fixture
def career_db(career_engine):
    Base.metadata.create_all(career_engine)
    with Session(career_engine) as db:
        db.add_all([User(id=1, username='alice', password_hash='test'), User(id=2, username='bob', password_hash='test')])
        db.flush()
        db.add_all([Resume(id=1, user_id=1, filename='resume.txt'),
                    JobDescription(id=1, user_id=1, title='Engineer', raw_text='Build APIs')])
        db.commit()
        yield db
