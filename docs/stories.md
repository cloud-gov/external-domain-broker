# Plan of attack

## Baseline

* Concourse pipeline
* Broker deploys to CF
* Registers with CF
* Provision call marks instance as requested
* Deprovision call marks instance for deletion
* Status call returns instance status
* Bind call does nothing

## Provisioning

* Provisions set of LE users
* Starts LE cert process
* Hands DNS information to user (how?)
* Detects when DNS is ready for `in progress` instances
* Finishes LE cert provisioning

* Creates CloudFront distribution
* Uploads cert to CloudFront distributions
* Uploads cert as new ALB listener on random ALB

## Deprovisioning

* Deprovisions LE cert
* Deprovisions LE user

## Renewals

* Determines certs ready for renewal
* Renews LE cert

## Migration

## Horizontal Scaling

* Only one process manages an instance at a time (worker queue?)
