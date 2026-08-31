from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token
)


password = "MiPassword123"


# Crear hash
hashed = hash_password(password)

print("Hash:")
print(hashed)


# Verificar contraseña correcta
print(
    "\nContraseña correcta:",
    verify_password(
        password,
        hashed
    )
)


# Verificar contraseña incorrecta
print(
    "Contraseña incorrecta:",
    verify_password(
        "incorrecta",
        hashed
    )
)


# Crear token
token = create_access_token(1)

print("\nToken:")
print(token)


# Decodificar token
payload = decode_access_token(token)

print("\nPayload:")
print(payload)