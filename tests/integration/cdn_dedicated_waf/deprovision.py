from broker.extensions import db


def subtest_deprovision_unsubscribe_sns_notification_topic(
    instance_model, tasks, service_instance, sns_commercial, service_instance_id="1234"
):
    sns_commercial.expect_unsubscribe_topic(
        service_instance.sns_notification_topic_subscription_arn
    )

    tasks.run_queued_tasks_and_enqueue_dependents()
    sns_commercial.assert_no_pending_responses()

    service_instance = db.session.get(instance_model, service_instance_id)
    assert service_instance.sns_notification_topic_subscription_arn == None
