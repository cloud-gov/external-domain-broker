from broker.models import change_instance_type, CDNDedicatedWAFServiceInstance
from broker.tasks.huey import pipeline_operation


@pipeline_operation("Changing instance type to CDNDedicatedWAFServiceInstance")
def change_to_cdn_dedicated_waf_instance_type(
    operation_id: int, *, operation, db, **kwargs
):
    service_instance = operation.service_instance
    service_instance = change_instance_type(
        service_instance, CDNDedicatedWAFServiceInstance, db.session
    )
    db.session.add(service_instance)
    db.session.commit()
