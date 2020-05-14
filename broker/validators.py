from openbrokerapi import errors
from typing import List

from .dns import get_cname, acme_challenge_cname_target, acme_challenge_cname_name


class CNAMEValidator:
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
        errors = []

        for d in domains:
            err = self._error_for_domain(d)

            if err:
                errors.append(err)

        return errors

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
