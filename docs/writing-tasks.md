# writing tasks

## Signature convention

Tasks are functions decorated with @huey.task. Huey persists tasks as a reference to 
the function being called, its args and kwargs, and the next task in the pipeline.
This means that if a function's signature changes, everything falls to pieces.
Because of this, and to make things easier to reason about, we have established a 
convention about non-scheduled task functions: the first argument is always an integer that is
the id of an Operation, and any other information a function needs should be passed as kwargs or 
persisted on the Operation or a related Model.

## idempotence

Tasks should be idempotent. This is important because most tasks are defined to be retryable,
and because the solution for stalling pipelines is to reenqueue the whole pipeline.
