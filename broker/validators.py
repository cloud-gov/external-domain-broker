import dns.resolver
from openbrokerapi import errors
from .config import config_from_env
from typing import List

config = config_from_env()


class CNAMEValidator:
    def __init__(self, domains):
        self.domains = domains
        self.resolver = dns.resolver.Resolver(configure=False)
        (nameserver, port) = config.DNS_VERIFICATION_SERVER.split(":")
        self.resolver.nameservers = [nameserver]
        self.resolver.port = int(port)

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
        cname = self._get_cname(domain)

        if not cname:
            return (
                f"CNAME {self._cname(domain)} should point to "
                f"{self._expected_cname(domain)}, but it does not exist."
            )

        if cname != self._expected_cname(domain):
            return (
                f"CNAME {self._cname(domain)} should point to "
                f"{self._expected_cname(domain)}, but it is set incorrectly to {cname}."
            )
        else:
            return ""

    def _get_cname(self, domain: str) -> str:
        try:
            answers = self.resolver.query(self._cname(domain), "CNAME")
            print(answers[0].target.to_text(omit_final_dot=True))

            return answers[0].target.to_text(omit_final_dot=True)

        except dns.resolver.NXDOMAIN:
            return ""

        except dns.resolver.NoAnswer:
            return ""

    def _expected_cname(self, domain: str) -> str:
        return f"_acme-challenge.{domain}.domains.cloud.gov"

    def _cname(self, domain: str) -> str:
        return f"_acme-challenge.{domain}"
