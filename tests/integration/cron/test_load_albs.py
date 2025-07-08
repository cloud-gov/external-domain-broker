from broker.models import DedicatedALB, DedicatedALBListener
from broker.tasks.cron import _load_albs


class FakeALBClient:
    def __init__(self, listener_alb_map: dict[str]):
        self.listener_alb_map = listener_alb_map
        self.describe_listeners_called = 0

    def describe_listeners(self, ListenerArns: list[str] = []):
        listeners = []
        for listener_arn in ListenerArns:
            load_balancer_arn = self.listener_alb_map[listener_arn]
            listeners.append(
                {
                    "ListenerArn": listener_arn,
                    "LoadBalancerArn": load_balancer_arn,
                }
            )
        self.describe_listeners_called += 1
        return {"Listeners": listeners}


def test_get_alb_listener_info(clean_db):
    fake_alb = FakeALBClient({"listener-1": "alb-1"})
    _load_albs(fake_alb, {"listener-1": "org-1"})
    _load_albs(fake_alb, {"listener-1": "org-1"})
    assert fake_alb.describe_listeners_called == 1


def test_load_albs(clean_db):
    fake_alb = FakeALBClient({"listener-1": "alb-1"})
    _load_albs(fake_alb, {"listener-1": "org-1"})

    albs = DedicatedALB.query.all()
    assert len(albs) == 1
    assert albs[0].alb_arn == "alb-1"
    assert albs[0].dedicated_org == "org-1"

    listeners = DedicatedALBListener.query.all()
    assert len(listeners) == 1
    assert listeners[0].dedicated_org == "org-1"
    assert listeners[0].alb_arn == "alb-1"
    assert listeners[0].listener_arn == "listener-1"
