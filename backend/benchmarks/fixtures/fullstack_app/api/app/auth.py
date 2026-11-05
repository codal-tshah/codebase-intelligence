from fastapi import Depends, HTTPException


def get_current_user(token: str = ""):
    if not token:
        raise HTTPException(status_code=401)
    return {"user": token}
