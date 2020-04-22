from . import db


class ServiceInstance(db.Model):
    id = db.Column(db.String, primary_key=True)
    status = db.Column(db.String, nullable=False)
    # TODO created_at? updated_at?
