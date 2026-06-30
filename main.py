from fastapi import *
from fastapi.security import *

from sqlalchemy.orm import Session

from database import *
from models import *
from auth import *


Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Mi API",
    version="1.0.0"
)

security=HTTPBearer()

@app.get("/health")
def health():
    return {
        "status": "ok"
    }

@app.get("/")
def home():
    return {"message":"API Online"}


@app.post("/register")
def register(
        username:str,
        password:str,
        db:Session=Depends(get_db)
):
    user=db.query(User).filter(
        User.username==username
    ).first()
    if user:
        raise HTTPException(
        status_code=400,
        detail="El usuario ya existe"
    )

    new_user=User(
        username=username,
        password=hash_password(password)
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"message":"registered"}


@app.post("/login")
def login(
        username:str,
        password:str,
        db:Session=Depends(get_db)
):
    user=db.query(User).filter(
        User.username==username
    ).first()
    if not user:
        raise HTTPException(
        status_code=401,
        detail="Usuario o contraseña incorrectos"
    )
    
    if not verify_password(
            password,
            user.password
    ):
        raise HTTPException(
        status_code=401,
        detail="Usuario o contraseña incorrectos"
    )

    token=create_token(username)

    return {
        "token":token
    }


@app.get("/profile")
def profile(
    cred:HTTPAuthorizationCredentials=Depends(security)
):
    user=verify_token(
        cred.credentials
    )
    return user