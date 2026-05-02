"""Pydantic schemas for auth endpoints."""

from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator


class RegisterRequest(BaseModel):
    email:     EmailStr
    password:  str
    full_name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token:  str
    token_type:    str = "bearer"
    user_id:       str
    email:         str
    full_name:     Optional[str] = None


class UserResponse(BaseModel):
    id:          str
    email:       str
    full_name:   Optional[str] = None
    is_active:   bool
    is_verified: bool


class UserUpdate(BaseModel):
    full_name:        Optional[str] = None
    email:            Optional[EmailStr] = None
    new_password:     Optional[str] = None
    current_password: Optional[str] = None  # required when changing email or password


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token:        str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v
