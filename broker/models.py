from openbrokerapi.service_broker import OperationState

from . import db
from .tasks import queue_all_provision_tasks_for_operation
import textwrap


class Base(db.Model):
    __abstract__ = True

    created_at = db.Column(db.TIMESTAMP(timezone=True), server_default=db.func.now())
    updated_at = db.Column(db.TIMESTAMP(timezone=True), onupdate=db.func.now())


class ACMEUser(Base):
    __tablename__ = "acme_user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String, nullable=False)
    uri = db.Column(db.String, nullable=False)
    private_key_pem = db.Column(db.Text, nullable=False)
    registration_json = db.Column(db.Text)
    service_instances = db.relation(
        "ServiceInstance", backref="acme_user", lazy="dynamic"
    )


class ServiceInstance(Base):
    id = db.Column(db.String(36), primary_key=True)
    operations = db.relation("Operation", backref="service_instance", lazy="dynamic")
    challenges = db.relation("Challenge", backref="service_instance", lazy="dynamic")
    acme_user_id = db.Column(db.Integer, db.ForeignKey("acme_user.id"))
    private_key_pem = db.Column(db.Text)
    csr_pem = db.Column(db.Text)
    domain_names = db.Column(db.JSON, default=[])

    def __repr__(self):
        return f"<ServiceInstance {self.id}>"

    @property
    def description(self):
        if self.challenges.count() == 0:
            return textwrap.dedent(
                """\
                    We're still attempting to provision your TLS
                    certificates. Once we're done, we'll provide
                    instructions on how to update DNS to finalize the
                    certificates.  This is a time-sensitive operation,
                    so please please wait 10 minutes and run this
                    command again.
                    """
            )
        else:
            desc = []
            desc.append("Please add the following TXT DNS records:")

            for challenge in self.challenges:
                d = challenge.validation_domain
                c = challenge.validation_contents
                desc.append(f"  {d} with contents {c}")

            desc.append(
                textwrap.dedent(
                    """\
                    We will detect those records and continue with the
                    domain creation.  Please allow time for the DNS
                    records to propagate and run this command again to
                    review status.
                    """
                )
            )

            return textwrap.dedent(" ".join(desc))


class Operation(Base):
    id = db.Column(db.Integer, primary_key=True)
    service_instance_id = db.Column(
        db.String, db.ForeignKey("service_instance.id"), nullable=False
    )
    state = db.Column(db.Enum(OperationState), nullable=False)

    def __repr__(self):
        return f"<Operation {self.id} {self.state}>"

    def queue_tasks(self):
        queue_all_provision_tasks_for_operation(self.id)


class Challenge(Base):
    id = db.Column(db.Integer, primary_key=True)
    service_instance_id = db.Column(
        db.String, db.ForeignKey("service_instance.id"), nullable=False
    )
    domain = db.Column(db.String, nullable=False)
    validation_domain = db.Column(db.String, nullable=False)
    validation_contents = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f"<Challenge {self.id} {self.domain}>"
