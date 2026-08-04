"""鉴权与 AES 加密单测(详设§2.19.6 / §4.2 错误码 / §6.4 依赖注入鉴权)。

涵盖：
- AES-256-GCM 密码加解密往返与校验(§2.19.6)。
- AES 会话令牌签发/校验/过期(§2.19.6，前后端 AES 加解密，无 JWT)。
- 登录端点信封(§2.21)与 40101 错误码(§4.2)。
"""

from __future__ import annotations

import os

import pytest

# 测试 AES_KEY(64 字符 hex；不与生产混用，conftest 已隔离 env)
os.environ.setdefault("AES_KEY", "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")

from cryptography.exceptions import InvalidTag  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from infra.security import crypto, token  # noqa: E402
from infra.security.token import (  # noqa: E402
    InvalidTokenError,
    create_access_token,
    decode_access_token,
)

_ = token  # 保留包导入用于覆盖检查


class TestAESCrypto:
    """§2.19.6 AES-256-GCM 密码加解密。"""

    def test_encrypt_decrypt_roundtrip(self) -> None:
        plain = "S3cr3t!Pass"
        enc = crypto.encrypt(plain)
        assert enc != plain  # 密文非明文
        assert crypto.decrypt(enc) == plain

    def test_verify_match(self) -> None:
        enc = crypto.encrypt("hello123")
        assert crypto.verify("hello123", enc) is True
        assert crypto.verify("wrong", enc) is False

    def test_decrypt_tampered_fails(self) -> None:
        enc = crypto.encrypt("data")
        # 篡改密文末尾(GCM 认证失败 -> InvalidTag)
        tampered = enc[:-4] + "AAAA"
        with pytest.raises(InvalidTag):
            crypto.decrypt(tampered)


class TestAESToken:
    """§2.19.6 AES 会话令牌(前后端 AES 加解密)。"""

    def test_create_and_decode(self) -> None:
        tok = create_access_token("admin")
        assert decode_access_token(tok) == "admin"

    def test_custom_ttl(self) -> None:
        tok = create_access_token("admin", ttl_minutes=1)
        assert decode_access_token(tok) == "admin"

    def test_expired_raises(self) -> None:
        # ttl=0 令创建即过期(边界；实际 expiry < now)
        tok = create_access_token("admin", ttl_minutes=-1)
        with pytest.raises(InvalidTokenError):
            decode_access_token(tok)

    def test_tampered_token_raises(self) -> None:
        with pytest.raises(InvalidTokenError):
            decode_access_token("not-a-valid-token!!")


@pytest.mark.db
class TestAuthAPI:
    """§2.21 信封 + §4.2 40101 + §6.4 鉴权依赖。"""

    @pytest.fixture()
    def client_with_admin(self, db_session: Session):
        """种子 admin 账户 + TestClient(get_db override 指向共享引擎；表已由 conftest db_session truncate)。"""
        from collections.abc import Iterator

        from sqlalchemy.orm import sessionmaker

        from api.deps import get_db
        from infra.db.models import AdminUser

        # conftest db_session 已 truncate 清表；复用其引擎建 TestSession(请求期隔离)
        TestSession = sessionmaker(bind=db_session.bind, autocommit=False, autoflush=False)
        with TestSession() as s:
            s.add(
                AdminUser(
                    username="admin",
                    password_encrypted=crypto.encrypt("InitPass123"),
                    must_change_password=True,
                )
            )
            s.commit()

        def _override_get_db() -> Iterator[Session]:
            db = TestSession()
            try:
                yield db
            finally:
                db.close()

        from api.main import create_app

        app = create_app()
        app.dependency_overrides[get_db] = _override_get_db

        with TestClient(app) as c:
            yield c

        app.dependency_overrides.clear()

    def test_login_success_envelope(self, client_with_admin: TestClient) -> None:
        """登录成功返回 7 字段信封 + access_token(§2.19.6)。"""
        resp = client_with_admin.post(
            "/api/v1/admin/login", json={"username": "admin", "password": "InitPass123"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {
            "code",
            "data",
            "source",
            "as_of",
            "disclaimer",
            "message",
            "trace_id",
        }
        assert body["code"] == 0
        assert body["data"]["access_token"]
        assert body["data"]["must_change_password"] is True

    def test_login_wrong_password_40101(self, client_with_admin: TestClient) -> None:
        """§4.2 密码错误 -> 40101 信封。"""
        resp = client_with_admin.post(
            "/api/v1/admin/login", json={"username": "admin", "password": "wrong"}
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["code"] == 40101
        assert body["data"] is None

    def test_protected_without_token_40101(self, client_with_admin: TestClient) -> None:
        """§4.2/§6.4 受保护端点未带令牌 -> 40101。"""
        resp = client_with_admin.get("/api/v1/admin/whoami")
        assert resp.status_code == 401
        assert resp.json()["code"] == 40101

    def test_protected_with_token_ok(self, client_with_admin: TestClient) -> None:
        """登录后带令牌访问受保护端点成功(§6.4)。"""
        tok = client_with_admin.post(
            "/api/v1/admin/login", json={"username": "admin", "password": "InitPass123"}
        ).json()["data"]["access_token"]
        resp = client_with_admin.get(
            "/api/v1/admin/whoami", headers={"Authorization": f"Bearer {tok}"}
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["username"] == "admin"

    def test_trigger_job_requires_auth_40101(self, client_with_admin: TestClient) -> None:
        """§3.14.4/§3.14.5 trigger-job 未带令牌 -> 40101。"""
        resp = client_with_admin.post("/api/v1/admin/trigger-job", json={"job": "fund_list"})
        assert resp.status_code == 401
        assert resp.json()["code"] == 40101

    def test_trigger_job_invalid_job_40001(self, client_with_admin: TestClient) -> None:
        """§3.14.4 trigger-job 鉴权通过但作业名非法 -> 40001。"""
        tok = client_with_admin.post(
            "/api/v1/admin/login", json={"username": "admin", "password": "InitPass123"}
        ).json()["data"]["access_token"]
        resp = client_with_admin.post(
            "/api/v1/admin/trigger-job",
            json={"job": "bogus"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == 40001
