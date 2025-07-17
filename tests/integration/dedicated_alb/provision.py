from broker.models import (
    DedicatedALB,
    DedicatedALBListener,
)


def create_dedicated_alb_listeners(
    db, organization_guid, dedicated_alb_id, dedicated_alb_arn
):
    alb_0 = DedicatedALB(
        alb_arn=dedicated_alb_arn,
        dedicated_org=organization_guid,
        id=dedicated_alb_id,
    )
    alb_1 = DedicatedALB(
        alb_arn="alb-our-arn-1",
        dedicated_org=organization_guid,
    )
    db.session.add_all(
        [
            alb_0,
            alb_1,
        ]
    )
    db.session.commit()

    our_listener_0 = DedicatedALBListener(
        listener_arn="our-arn-0",
        alb_arn=dedicated_alb_arn,
        dedicated_org=organization_guid,
    )
    our_listener_1 = DedicatedALBListener(
        listener_arn="our-arn-1",
        alb_arn="alb-our-arn-1",
        dedicated_org=organization_guid,
    )

    db.session.add_all(
        [
            our_listener_0,
            our_listener_1,
        ]
    )
    db.session.commit()
    db.session.expunge_all()
