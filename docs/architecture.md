# Architecture

The broker consists of two main processes:
- the API, which CAPI talks to
- the workers, which do the actual provisioning/updating/deprovisioning

There are two datastores:
- postgres for persistent storage about service instances
- redis, for non-durable task storage

## Shared Codebase

The API and the workers exist in the same codebase. This is necessary, but creates complications.
The big complication is that the API was written to use flask-sqlalchemy for its models. This means
that to leverage the same models, the workers have to use flask-sqlalchemy as well, or attempt to
duplicate the same models in raw sqlalchemy. Because of this, the workers all must initialize a flask
app which is used only to inject an app context to make flask-sqlalchemy happy. 

## API
The API is a flask app, built using [the python openbrokerapi
package](https://github.com/eruvanos/openbrokerapi).

## Workers

The workers are huey consumers. Huey is really designed to be run as one consumer that spins off 
its own child worker processes, but we have it running as many consumers with only one child worker each
to fit better into CloudFoundry.

### CloudFoundry challenges

#### Scheduled tasks

As mentioned above, we're doing something huey doesn't really expect and running N consumers. This creates
a main issue that scheduled tasks get picked up by every consumer. We're dealing with this currently by 
having the consumers exit cron tasks early if they're not instance 0.

#### Consumer Shutdowns

Huey wants to be shut down with a SIGINT, and CloudFoundry shuts apps down with SIGTERM. Because of 
the way huey handles tasks (a pipeline is a linked list of tasks, so the whole list is popped
from Redis whenever a task is consumed), this means that if a task is running as part of a pipeline
when an app container gets terminated, the pipeline gets completely lost. The current solution for
this is to scan periodically for operations in-progress that have been idle for longer than expected
and reenqueue their whole associate pipeline. A *major* downside to this is that a task in a retry
loop will restart its retry count if it happens to get caught here.
