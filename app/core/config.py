import os

from dotenv import load_dotenv


load_dotenv()


class Settings:

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        ""
    )

    JWT_SECRET: str = os.getenv(
        "JWT_SECRET",
        ""
    )

    JWT_ALGORITHM: str = os.getenv(
        "JWT_ALGORITHM",
        "HS256"
    )

    JWT_EXPIRE_MINUTES: int = int(
        os.getenv(
            "JWT_EXPIRE_MINUTES",
            "60"
        )
    )


settings = Settings()