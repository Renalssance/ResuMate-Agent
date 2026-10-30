from backend.auth.security import get_password_hash, verify_password


def test_pbkdf2_passwords_still_verify_without_passlib():
    password_hash = get_password_hash("secret")
    assert verify_password("secret", password_hash)
    assert not verify_password("wrong", password_hash)
    assert not verify_password("secret", "$2b$legacy-bcrypt-hash")
