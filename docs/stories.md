# Plan of attack

## Baseline

* Concourse pipeline
* Broker deploys to CF
* Registers with CF
* Advertises two plans (ALB & CloudFront)
* Provision call marks instance as requested
* Deprovision call marks instance for deletion
* Status call returns instance status
* Bind call does nothing

## Provisioning

* Creates LE user per cert
* Starts LE cert process
* Hands DNS information to user (via instance status)
* Detects when DNS is ready for `in progress` instances.  Can we just ping LE over and over?
* Finishes LE cert provisioning
* Creates CloudFront distribution.
* Connects the cert S3 bucket to the distribution (for renewals).
* Hook up S3 to ALB listener? How does this even work?  Maybe the broker needs to answer?
* Uploads cert to ACM
* Connects cert to CloudFront distributions
* Connects cert as new ALB listener on random ALB

## Renewals

* Determines certs ready for renewal (10 days to expiration)
* Investigate whether we need S3 for renewals.  Is an existing valid LE cert enough?
* Issue HTTP01 challenge
* Update file in S3 to answer challenge
* Finalize challenge with LE

## Migration

* Investigate CF migrate service.
* Idempotent script to migrate existing everything

## Horizontal Scaling

* Only one process manages an instance at a time (worker queue?)

# After Launch

* Create CF distribution early with `UUID.cloud.gov` domain to facilitate security scanning
* Uploads cert to least-utilized ALB listener
* Should the broker create ALBs?

## Deprovisioning

* Deprovisions LE cert
* Deprovisions LE user
