import dns.resolver
from openbrokerapi import errors
from .config import config_from_env

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
                "We could not find a CNAME record for some of your domains.",
                "Please ensure the following DNS records are in place and",
                "try to provision this service again:",
            ]

            for error in instructions:
                msg.append("  " + error)

            raise errors.ErrBadRequest("\n".join(msg))

    def _instructions(self, domains: list):
        errors = []

        for d in domains:
            err = self._error_for_domain(d)

            if err:
                errors.append(err)

        return errors

    def _error_for_domain(self, domain):
        if self._missing_cname(domain):
            return (
                f"CNAME _acme-challenge.{domain} "
                f"should point to "
                f"_acme-challenge.{domain}.domains.cloud.gov, "
                f"but it does not exist."
            )
        else:
            return ""

    def _missing_cname(self, domain):
        challenge_domain = "_acme-challenge." + domain
        try:
            self.resolver.query(challenge_domain, "CNAME")

        except dns.resolver.NXDOMAIN:
            return True

        except dns.resolver.NoAnswer:
            return True

        return False
