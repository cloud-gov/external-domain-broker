# Cloud Foundry Domain Broker

Cloud Foundry service broker to manage AWS CloudFront, AWS ALBs and Let's Encrypt.

Like the [cf-domain-broker](https://github.com/18F/cf-domain-broker), this
broker combines the features of the
[cf-cdn-service-broker](https://github.com/18F/cf-cdn-service-broker) and
the [cf-domain-broker-alb](https://github.com/18F/cf-domain-broker-alb). It
provisions Let's Encrypt certificates for a given domain, and configures
either AWS ALBs (created out-of-band) or an AWS CloudFront distribution
(created by the broker) to use that certificate.

## AWS GovCloud

It's important to note this broker and it's configuration was designed first
and foremost for AWS GovCloud, which has some limitations when it comes to
global configurations. For example, Route53 is not avaialble in GovCloud as
it's a global service, so while the domain broker can be deployed as a Cloud
Foundry app in GovCloud, it still needs to cross the boundary into the AWS
commercial cloud.

This also means the broker expects to use a different IAM user and configuration
for ALBs and CloudFront distributions.

## Usage

When users request a domain service instance, this broker will validate some
prerequisite DNS configuration then provision a Let's Encrypt certificate, 
an ELB and a CloudFront CDN, and wire them all up together. 

### Let's Encrypt Challenge Challenges

We have some constraints that make the [Let's Encrypt Challenge
process](https://letsencrypt.org/docs/challenge-types/) "difficult":

#### `HTTP01`

`HTTP01` with CloudFront gives us a chicken-and-egg problem, in that CloudFront
will not answer to a custom domain, even for HTTP, without [verifying ownership
of that domain via a valid SSL
certificate](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cnames-and-https-requirements.html#https-requirements-certificate-issuer):

> If you want to use an alternate domain name with your CloudFront
> distribution, you must verify to CloudFront that you have authorized rights
> to use the alternate domain name. To do this, you must attach a valid
> certificate to your distribution, and make sure that the certificate comes
> from a trusted CA that is listed on the Mozilla Included CA Certificate List.
> **CloudFront does not allow you to use a self-signed certificate to verify your
> authorized rights to use an alternate domain name.**

#### `TLS-ALPN01`

We still need to fully investigate `ALPN01`, and its support in CloudFront.
It's not clear if the `ALPN01` certificate is a self-signed cert - if so, we'll
likely hit the same CloudFront limitation listed above.

Investigation pointers:

- [CloudFront supports HTTP/2](https://aws.amazon.com/about-aws/whats-new/2016/09/amazon-cloudfront-now-supports-http2/)
- [ALPN is the required SSL implementation for HTTP/2](https://en.wikipedia.org/wiki/Application-Layer_Protocol_Negotiation)
- [Dehydrate](https://github.com/lukas2511/dehydrated/blob/master/docs/tls-alpn.md) bash ACME client can generate ALPN certs.

#### `DNS01`

We do not have access to or control over DNS for the application, so we cannot
automate the `DNS01` challenge.

#### Our Solution - CNAMES of CNAMES

Because of these limitations, we have users create CNAME (or ALIAS) records pointing
to records within our control. This allows us to validate the user's input ahead of time,
hopefully reducing the number of failures at provision time. It also allows us to manage
renewals using TXT records, which eliminates the S3 config from the previous iterations
of the broker. Finally, it should make creating a process to change between CDN and ALB
instances possible without risk of downtime.

Before creation, customers create a CNAME record for `_acme-challenge.<their-domain>`
pointed to `_acme-challenge.<their-domain>.<our-configured-domain>`. This allows us to
update TXT records on their behalf, which in turn allows us to solve DNS-01 challenges for
them.
Before, during, or after provisioning, they add a CNAME record for `<their-domain>` pointing
to `<their-domain>.<our-configured-domain>`, which routes traffic to their site.

## Configuration

The Broker can be configured via the following environment variables:

| Variable                         |                                                             |
| ---------------------------------|-------------------------------------------------------------|
| FLASK_ENV                        | Environment name for Flask                                  |
| SECRET_KEY                       | Flask secret key                                            |
| BROKER_USERNAME                  | Username for the broker                                     |
| BROKER_PASSWORD                  | Password for the broker                                     |
| DATABASE_ENCRYPTION_KEY          | Key used to encrypt database storage                        |
| ROUTE53_ZONE_ID                  | Zone ID of Route53 zone for hosted zone for DNS_ROOT_DOMAIN |
| DNS_ROOT_DOMAIN                  | Intermediate domain users point their DNS to                |
| DEFAULT_CLOUDFRONT_ORIGIN        | CloudFront origin used for instances that route to CF apps  |
| AWS_GOVCLOUD_REGION              | Region to use for AWS govcloud services                     |
| AWS_GOVCLOUD_SECRET_ACCESS_KEY   | Access key for AWS govcloud services                        |
| AWS_GOVCLOUD_ACCESS_KEY_ID       | Access key ID for AWS govcloud services                     |
| AWS_COMMERCIAL_REGION            | Region to use for commercial AWS services                   |
| AWS_COMMERCIAL_SECRET_ACCESS_KEY | Access key for commercial AWS services                      |
| AWS_COMMERCIAL_ACCESS_KEY_ID     | Access key ID for commercial AWS services                   |
| ALB_LISTENER_ARNS                | comma-separated list of ARNs for AWS ALB Listeners to use   |
| SMTP_HOST                        | Hostname of SMTP server (for alerts)                        |
| SMTP_PORT                        | Port for SMTP server (for alerts)                           |
| SMTP_CERT                        | Certificate chain to trust for SMTP server (for alerts)     |
| SMTP_USER                        | Username for authentication with SMTP server (for alerts)   |
| SMTP_PASS                        | Password to use for SMTP server (for alerts)                |
| SMTP_FROM                        | Email address to send emails from (for alerts)              |
| SMTP_TO                          | Email address to send alert emails to                       |

## IAM Policies

As this broker manages ELBs, IAM Certificates, CloudFront and other
AWS resources, it requires an IAM policy that allows access to those APIs.
We've [provided a sample policy](/doc/sample_iam_policy.json), but you're
responsible for auditing your own security policies. No warranty, etc, etc.

## Pipeline Configuration

This broker leverages [Concourse](https://concourse-ci.org) for its deployment
automation, but it's not dependent on it. You can find example and live
concourse configuration files in [the `ci/` directory](/ci).

## History

This broker supersedes the
[cf-domain-broker](https://github.com/18F/cf-domain-broker), the
[cf-cdn-service-broker](https://github.com/18F/cf-cdn-service-broker) and
the [cf-domain-broker-alb](https://github.com/18F/cf-domain-broker-alb).
