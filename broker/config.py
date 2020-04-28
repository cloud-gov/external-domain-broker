"""Flask config class."""
import os

from environs import Env

base_dir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class ProdConfig(Config):
    env = Env()
    TESTING = False
    DEBUG = False
    SECRET_KEY = env("SECRET_KEY")
    BROKER_USERNAME = env("BROKER_USERNAME")
    BROKER_PASSWORD = env("BROKER_PASSWORD")
    SQLALCHEMY_DATABASE_URI = env("DATABASE_URL")


class TestConfig(Config):
    TESTING = True
    DEBUG = True
    SQLITE_DB_PATH = os.path.join(base_dir, "dev.sqlite")
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + SQLITE_DB_PATH
    SECRET_KEY = "Sekrit Key"
    BROKER_USERNAME = "broker"
    BROKER_PASSWORD = "sekrit"


config = {"test": TestConfig, "prod": ProdConfig}
