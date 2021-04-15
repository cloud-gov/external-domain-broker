import re
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

        # track the CNAMEs we've resolved to check for loops
        visited_cnames = [acme_challenge_cname_name(domain)]

        if not cname:
            return (
                f"CNAME {acme_challenge_cname_name(domain)} should point to "
                f"{acme_challenge_cname_target(domain)}, but it does not exist."
            )

        while cname:
            if cname == acme_challenge_cname_target(domain):
                return ""
            last_resolved_cname = cname
            visited_cnames.append(cname)
            cname = get_cname(last_resolved_cname)
            if cname in visited_cnames:
                return f"Loop detected in CNAMEs - {cname} points to itself. Resolution chain: {visited_cnames} "

        return (
            f"CNAME {acme_challenge_cname_name(domain)} should point to "
            f"{acme_challenge_cname_target(domain)}, but it is set incorrectly to {last_resolved_cname}."
        )


class UniqueDomains:
    def __init__(self, domains):
        self.domains = domains

    def validate(self, ignore_instance: ServiceInstance = None):
        instructions = self._instructions(self.domains, ignore_instance)

        if instructions:
            msg = [
                "An external domain service already exists for the following domains:"
            ]

            for error in instructions:
                msg.append("  " + error)

            raise errors.ErrBadRequest("\n".join(msg))

    def _instructions(
        self, domains: List[str], ignore_instance: ServiceInstance = None
    ) -> List[str]:
        return [
            self._error_for_domain(d, ignore_instance)
            for d in domains
            if self._error_for_domain(d, ignore_instance)
        ]

    def _error_for_domain(
        self, domain: str, ignore_instance: ServiceInstance = None
    ) -> str:
        if ignore_instance:
            count = ServiceInstance.query.filter(
                ServiceInstance.deactivated_at == None,  # noqa: E711
                ServiceInstance.domain_names.has_key(domain),
                ServiceInstance.id != ignore_instance.id,
            ).count()
        else:
            count = ServiceInstance.query.filter(
                ServiceInstance.deactivated_at == None,  # noqa: E711
                ServiceInstance.domain_names.has_key(domain),
            ).count()

        if count:
            return domain
        else:
            return ""


class ErrorResponseConfig:
    # CloudFront only allows us to configure these ones
    VALID_ERROR_CODES = [
        "400",
        "403",
        "404",
        "405",
        "414",
        "416",
        "500",
        "501",
        "502",
        "503",
        "504",
    ]

    def __init__(self, input):
        self.input = input

    def validate(self):
        if not isinstance(self.input, dict):
            raise errors.ErrBadRequest(
                "error_response should be a dictionary of error code: response path"
            )
        for key, value in self.input.items():
            if key not in ErrorResponseConfig.VALID_ERROR_CODES:
                raise errors.ErrBadRequest("error_response keys must be strings")
            if not isinstance(value, str):
                raise errors.ErrBadRequest("error_response values must be strings")
            if not value:
                raise errors.ErrBadRequest("error_response values must not be empty")
            if not value[0] == "/":
                raise errors.ErrBadRequest(
                    "error_response path must be a path starting with `/`"
                )


class HeaderList:
    # most clearly stated here: https://tools.ietf.org/html/rfc7230#section-3.2.6
    ALLOWED_CHARACTERS = set(
        r"!#$%&'*+-.0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ^_`abcdefghijklmnopqrstuvwxyz|"
    )

    def __init__(self, header_list):
        self.header_list = header_list

    def validate(self):
        for header in self.header_list:
            if not header:
                raise errors.ErrBadRequest("Headers cannot be empty")
            header_chars = set(header)
            if not header_chars.issubset(HeaderList.ALLOWED_CHARACTERS):
                invalid_characters = header_chars.difference(
                    HeaderList.ALLOWED_CHARACTERS
                )
                raise errors.ErrBadRequest(
                    f"{header} contains these invalid characters: {invalid_characters}"
                )


class Hostname:
    # a hostname consists of a set of 1-63 nodes, separated by dots, up to 253 characters in total
    # each node consists of 1-63 characters
    # because these need internet domain names, the final node needs to be a root domain, which must be at least two characters
    # a node
    # - starts and ends with a letter or number
    # - may contain letters, numbers, and dashes
    # - must contain at least one character
    # - must contain at most 63 characters
    # - is case-insensitive

    domain_name = re.compile(
        r"""^
(                                                   # start node
    (                                               # start node label
        ([a-zA-Z0-9])|                              # special case for single-character label
        ([a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]) # labels start & end w/non-hyphen char. 1-63 chars, 1 char case handled above
    )                                               # end node label
     \.                                             # dot at the end of the node
)                                                   # end node.
{1,62}                                              # cound non-tld nodes. At least 1, (we want hostnames). Up to 63 nodes allowed, one more below
     [a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]      # tld node needs to be at least 2 characters
        """,
        re.VERBOSE,
    )

    def __init__(self, origin):
        self.origin = origin

    def validate(self):

        if not re.fullmatch(Hostname.domain_name, self.origin):
            raise errors.ErrBadRequest(f"{self.origin} is not a valid hostname")
        if len(self.origin) > 253:
            raise errors.ErrBadRequest(f"{self.origin} is not a valid hostname")
