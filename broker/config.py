"""Flask config class."""
from environs import Env


class Config:
    """Set Flask configuration variables."""

    env = Env()

    BROKER_USERNAME = env("BROKER_USERNAME")
    BROKER_PASSWORD = env("BROKER_PASSWORD")

    TESTING = env("TESTING", False)
    DEBUG = env("DEBUG", False)
    SECRET_KEY = env("SECRET_KEY")

    SQLALCHEMY_DATABASE_URI = env("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
