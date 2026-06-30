from pwdlib import PasswordHash
import jwt
import os
from dotenv import load_dotenv

load_dotenv()

pwd = PasswordHash.recommended()

SECRET = os.getenv("JWT_SECRET")

def hash_password(password):
    return pwd.hash(password)

def verify_password(password, hashed):
    return pwd.verify(password, hashed)

def create_token(username):
    return jwt.encode(
        {"user": username},
        SECRET,
        algorithm="HS256"
    )

def verify_token(token):
    return jwt.decode(
        token,
        SECRET,
        algorithms=["HS256"]
    )