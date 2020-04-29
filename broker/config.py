"""Flask config class."""
import os

from environs import Env

base_dir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class ProdConfig(Config):
    TESTING = False
    DEBUG = False

    def __init__(self):
        self.env = Env()

    @property
    def SECRET_KEY(self):
        return self.env("SECRET_KEY")

    @property
    def BROKER_USERNAME(self):
        return self.env("BROKER_USERNAME")

    @property
    def BROKER_PASSWORD(self):
        return self.env("BROKER_PASSWORD")

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        return self.env("DATABASE_URL")


class TestConfig(Config):
    TESTING = True
    DEBUG = True
    SQLITE_DB_PATH = os.path.join(base_dir, "..", "dev.sqlite")
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + SQLITE_DB_PATH
    SECRET_KEY = "Sekrit Key"
    BROKER_USERNAME = "broker"
    BROKER_PASSWORD = "sekrit"


def config(env):
    mapping = {
        "test": TestConfig,
        "prod": ProdConfig,
    }
    return mapping[env]()
