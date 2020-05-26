import pytest
from flask import current_app


class Tasks:
    def __init__(self):
        self.huey = current_app.huey

    def run_pipeline_stages(self, num_pipeline_stages: int):
        """
        Runs run_all_queued_without_pipelines the specified number of times.

        Will fail the test if there's not at least a single Task to be run.
        """

        for _ in range(num_pipeline_stages):
            self.run_all_queued_without_pipelines()

    def run_all_queued_without_pipelines(self):
        """
        Runs all currently queued tasks.  Enqueues pipeline tasks (created with
        `Task.then()`) for the next call of run_all_queued_without_pipelines,
        but does not execute them.  This is useful for stepping through
        pipeline stages in your tests.

        You could also call run_all_queued_including_pipelines, but that's
        slower and less controlled, resulting in confusing test failures from
        later pipeline stages.

        Will fail the test if there's not at least a single Task to be run.
        """
        # __tracebackhide__ = True

        found_at_least_one_queued_task = False
        task = self.huey.dequeue()
        pipeline_tasks = []

        while task:
            found_at_least_one_queued_task = True
            task.execute()

            if task.on_complete:
                pipeline_tasks.append(task.on_complete)
            task = self.huey.dequeue()

        for task in pipeline_tasks:
            self.huey.enqueue(task)

        if not found_at_least_one_queued_task:
            pytest.fail("No tasks queued to run.")

    def run_all_queued_including_pipelines(self):
        """
        Runs all currently queued tasks and their pipelines, created with
        `Task.then()`.

        Will fail the test if there's not at least a single Task to be run.
        """
        # __tracebackhide__ = True

        found_at_least_one_queued_task = False
        task = self.huey.dequeue()

        while task:
            found_at_least_one_queued_task = True
            task.execute()

            if task.on_complete:
                task = task.on_complete
            else:
                task = self.huey.dequeue()

        if not found_at_least_one_queued_task:
            pytest.fail("No tasks queued to run.")


@pytest.fixture(scope="function")
def tasks():
    return Tasks()
