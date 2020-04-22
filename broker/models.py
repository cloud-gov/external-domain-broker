from .db import TIMESTAMP, Column, Model, String, Text, func


class TimestampMixin(object):
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now())


class ServiceInstance(Model, TimestampMixin):
    id = Column(String, length=36, primary_key=True)
    status = Column(Text, nullable=False)
