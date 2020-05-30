import dns.resolver

from broker.extensions import config

(_nameserver, _port) = config.DNS_VERIFICATION_SERVER.split(":")
_root_dns = config.DNS_ROOT_DOMAIN
_resolver = dns.resolver.Resolver(configure=False)
_resolver.nameservers = [_nameserver]
_resolver.port = int(_port)


def get_cname(domain: str) -> str:
    try:
        answers = _resolver.query(domain, "CNAME")

        return answers[0].target.to_text(omit_final_dot=True)

    except dns.resolver.NXDOMAIN:
        return ""

    except dns.resolver.NoAnswer:
        return ""


def acme_challenge_cname_target(domain: str) -> str:
    return f"_acme-challenge.{domain}.{_root_dns}"


def acme_challenge_cname_name(domain: str) -> str:
    return f"_acme-challenge.{domain}"
