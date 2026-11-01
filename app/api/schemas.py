from typing import Literal

from pydantic import BaseModel


class ClientMessage(BaseModel):
    """Client (mobile/web/terminal) server ku anuppura message format."""

    type: Literal["message", "reset"]
    text: str = ""