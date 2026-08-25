"""可选 JWT 登录；关闭时保持公开作品 Demo 的匿名行为。"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from chapter07_cs2_coach.database import StoredUser, create_database_engine


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class LoginRequest(RegisterRequest):
    pass


class UserResponse(BaseModel):
    id: str
    email: EmailStr


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class AuthConfigurationError(RuntimeError):
    pass


class InvalidCredentialsError(RuntimeError):
    pass


class EmailAlreadyExistsError(RuntimeError):
    pass


class AuthService:
    def __init__(
        self,
        *,
        enabled: bool,
        engine: Engine | None = None,
        jwt_secret: str = "",
        token_minutes: int = 60 * 24 * 7,
    ) -> None:
        self.enabled = enabled
        self.engine = engine
        self.jwt_secret = jwt_secret
        self.token_minutes = token_minutes
        self.password_hash = PasswordHash.recommended()
        if enabled and (engine is None or len(jwt_secret) < 32):
            raise AuthConfigurationError(
                "启用登录需要 DATABASE_URL 和至少 32 字符的 ROUNDMIND_JWT_SECRET。"
            )

    @classmethod
    def from_environment(cls) -> "AuthService":
        enabled = os.getenv("ROUNDMIND_AUTH_REQUIRED", "false").lower() == "true"
        if not enabled:
            return cls(enabled=False)
        database_url = os.getenv("DATABASE_URL", "").strip()
        return cls(
            enabled=True,
            engine=create_database_engine(database_url) if database_url else None,
            jwt_secret=os.getenv("ROUNDMIND_JWT_SECRET", ""),
        )

    def register(self, email: str, password: str) -> TokenResponse:
        self._require_enabled()
        normalized = email.strip().casefold()
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session, session.begin():
            if session.scalar(select(StoredUser).where(StoredUser.email == normalized)):
                raise EmailAlreadyExistsError("该邮箱已经注册。")
            user = StoredUser(
                id=str(uuid4()),
                email=normalized,
                password_hash=self.password_hash.hash(password),
                created_at=now,
            )
            session.add(user)
            user_id, user_email = user.id, user.email
        return self._token(user_id, user_email)

    def login(self, email: str, password: str) -> TokenResponse:
        self._require_enabled()
        with Session(self.engine) as session:
            user = session.scalar(
                select(StoredUser).where(StoredUser.email == email.strip().casefold())
            )
            if user is None or not self.password_hash.verify(password, user.password_hash):
                raise InvalidCredentialsError("邮箱或密码错误。")
            return self._token(user.id, user.email)

    def verify_token(self, token: str) -> UserResponse:
        self._require_enabled()
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=["HS256"],
                options={"require": ["sub", "exp", "iat"]},
            )
        except jwt.PyJWTError as error:
            raise InvalidCredentialsError("登录状态无效或已过期。") from error
        with Session(self.engine) as session:
            user = session.get(StoredUser, payload["sub"])
            if user is None:
                raise InvalidCredentialsError("用户不存在。")
            return UserResponse(id=user.id, email=user.email)

    def _token(self, user_id: str, email: str) -> TokenResponse:
        now = datetime.now(timezone.utc)
        encoded = jwt.encode(
            {"sub": user_id, "iat": now, "exp": now + timedelta(minutes=self.token_minutes)},
            self.jwt_secret,
            algorithm="HS256",
        )
        return TokenResponse(
            access_token=encoded,
            user=UserResponse(id=user_id, email=email),
        )

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise AuthConfigurationError("登录功能尚未启用。")
