from typing import List

from openbrokerapi import errors

from broker.dns import acme_challenge_cname_name, acme_challenge_cname_target, get_cname
from broker.models import ServiceInstance


class CNAME:
    def __init__(self, domains):
        self.domains = domains

    def validate(self):
        instructions = self._instructions(self.domains)

        if instructions:
            msg = [
                "We could not find correct CNAME records for one or more of your domains.",
                "Please ensure the following DNS records are in place and try to provision",
                "this service again:",
            ]

            for error in instructions:
                msg.append("  " + error)

            raise errors.ErrBadRequest("\n".join(msg))

    def _instructions(self, domains: List[str]) -> List[str]:
        return [self._error_for_domain(d) for d in domains if self._error_for_domain(d)]

    def _error_for_domain(self, domain: str) -> str:
        cname = get_cname(acme_challenge_cname_name(domain))

        if not cname:
            return (
                f"CNAME {acme_challenge_cname_name(domain)} should point to "
                f"{acme_challenge_cname_target(domain)}, but it does not exist."
            )

        if cname != acme_challenge_cname_target(domain):
            return (
                f"CNAME {acme_challenge_cname_name(domain)} should point to "
                f"{acme_challenge_cname_target(domain)}, but it is set incorrectly to {cname}."
            )
        else:
            return ""


class UniqueDomains:
    def __init__(self, domains):
        self.domains = domains

    def validate(self):
        instructions = self._instructions(self.domains)

        if instructions:
            msg = [
                "An external domain service already exists for the following domains:"
            ]

            for error in instructions:
                msg.append("  " + error)

            raise errors.ErrBadRequest("\n".join(msg))

    def _instructions(self, domains: List[str]) -> List[str]:
        return [self._error_for_domain(d) for d in domains if self._error_for_domain(d)]

    def _error_for_domain(self, domain: str) -> str:
        count = ServiceInstance.query.filter(
            ServiceInstance.deactivated_at == None,  # noqa: E711
            ServiceInstance.domain_names.has_key(domain),
        ).count()

        if count:
            return domain
        else:
            return ""
