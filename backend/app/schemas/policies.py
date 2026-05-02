"""Pydantic schemas for policy endpoints."""

from pydantic import BaseModel


class CreatePolicyRequest(BaseModel):
    policy_data:  dict
    workspace_id: str


class UpdatePolicyRequest(BaseModel):
    policy_data: dict


class PolicyResponse(BaseModel):
    id:            str
    policy_number: str
    policy_type:   str = None
    policy_data:   dict = None
    status:        str = None
    created_at:    str = None
    updated_at:    str = None
