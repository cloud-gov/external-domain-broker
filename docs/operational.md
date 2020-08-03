# Operational docs
## tips and tricks for running this thing IRL


### Things to keep in mind

Huey pipelines are linked-list tasks. This means that when Huey pulls a task out of the queue,
and that task is part of a pipeline, the whole pipeline is popped from the queue. Because of this,
if the worker consuming a task terminates without pushing the pipeline back to the queue, Huey loses
track of the pipeline. This lead to the creation of the `scan_for_stalled_pipelines` job, which runs
on a cron schedule. It looks for pipelines that have not been updated in long enough that it appears
they're not running. When such pipelines are detected, they're re-enqueued from the start.

### Stopping pipelines by hand

Sometimes, a pipeline might be running, and you may want to make it stop. You can do this 
by connecting to the database and updating the Operation's `canceled_at` field:

```
sql> UPDATE operation SET canceled_at = now() WHERE id = <operation_id>;
```

### Restarting a pipeline

Sometimes it's useful to restart a pipeline manually, for instance if a pipeline is failing
on a step, and you know rerunning a previous step is likely to fix it.
Start by stopping the pipeline as described above. Then wait for the pipeline to attempt to
rerun the next task (normally ten minutes should be sufficient). Finally, update the `operation`
so the stalled pipeline scanner re-enqueues it:

```
sql> UPDATE operation SET canceled_at = null WHERE id = <operation_id>;
```

### Updating an instance by hand

Any operation that CAPI might do can be done by:
1. updating the service_instance record
2. creating an appropriate operation record
This is because of the scan_for_stalled_pipelines job.

*note: this bypasses a lot of validation, so proceed with care.*

Before doing any of the below, you should make sure there are no operations in progress:
```
sql> SELECT id FROM operation WHERE
        service_instance_id = <service_instance_id> AND
        state = 'in progress' AND
        canceled_at IS NULL;
```

Example: Someone, for some reason, ran `cf purge-service-instance <service_instance>`,
but we need to delete the service instance from the broker so the AWS resources get cleaned up.
All we need to do is create a record in the `operation` table and wait:

```
sql> INSERT INTO operation (service_instance_id, updated_at, action, state)
        VALUES (<service_instance_id>, now(), 'Deprovision', 'in progress');
```

This could also be used to force an early renewal of a certificate:

```
sql> INSERT INTO operation (service_instance_id, updated_at, action, state)
        VALUES (<service_instance_id>, now(), 'Renewal', 'in progress');
```
