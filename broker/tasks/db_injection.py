import functools

from flask import Flask
from broker.extensions import db, config

def inject_db(func):
    """
    Push an app context to a function and add a db the function's arguments.
    This allows us to share the flask_sqlalchemy-created models in huey.
    Make sure this decorator is below any huey decorators
    """
    @functools.wraps(func)
    def injected(*args, **kwargs):
        app = Flask(__name__)
        app.config.from_object(config)
        with app.app_context():
            db.init_app(app)
            kwargs['db'] = db
            return func(*args, **kwargs)

    return injected
