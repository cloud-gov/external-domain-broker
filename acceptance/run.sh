#!/usr/bin/env bash

# This acceptance test run in CI against a live CF instance, and provisions
# production Let's Encrypt certificates.  The domains (DOMAIN_0 & DOMAIN_1)
# should each be pre-configured in DNS like such:
# 
# CNAME $DOMAIN -> $DOMAIN.$DNS_ROOT_DOMAIN
# CNAME _acme-challenge.$DOMAIN -> _acme-challenge.$DOMAIN.$DNS_ROOT_DOMAIN
#
# ($DNS_ROOT_DOMAIN is the value the broker is configured with)

INSTANCE="external-domain-broker-test-${RANDOM}"

required_vars=(
  CF_API_URL
  CF_ORGANIZATION
  CF_PASSWORD
  CF_SPACE
  CF_USERNAME
  DNS_ROOT_DOMAIN
  HOSTED_ZONE_ID
  TEST_DOMAIN
  PLAN_NAME
  SERVICE_NAME
)

unset_vars=()
for var in "${required_vars[@]}"; do
  [[ -v $var ]] || unset_vars+=("$var")
done

if [ ${#unset_vars[@]} -gt 0 ]; then
  echo "Missing environment variables:"
  for var in "${unset_vars[@]}"; do
    echo "  \$$var"
  done
  exit 3
fi

set -euxo pipefail

trap cleanup EXIT

main() {
  login
  cleanup
  prep_domains
  tests
  echo "Congratulations!  The tests pass!"
}

login() {
  cf api "$CF_API_URL"
  (set +x; cf auth "$CF_USERNAME" "$CF_PASSWORD")
  cf target -o "$CF_ORGANIZATION" -s "$CF_SPACE"
}

prep_domains() {
  DOMAIN_0="test-${RANDOM}.${TEST_DOMAIN}"
  DOMAIN_1="test-${RANDOM}.${TEST_DOMAIN}"
  cat << EOF > ./create-cname.json
{
  "Changes": [
    {
      "Action": "CREATE",
      "ResourceRecordSet": {
        "Name": "${DOMAIN_0}.",
        "Type": "CNAME",
        "TTL": ${TTL},
        "ResourceRecords": [
          {"Value": "${DOMAIN_0}.${DNS_ROOT_DOMAIN}."}
        ]
      }
    },
    {
      "Action": "CREATE",
      "ResourceRecordSet": {
        "Name": "_acme-challenge.${DOMAIN_0}.",
        "Type": "CNAME",
        "TTL": ${TTL},
        "ResourceRecords": [
          {"Value": "_acme-challenge.${DOMAIN_0}.${DNS_ROOT_DOMAIN}."}
        ]
      }
    },
    {
      "Action": "CREATE",
      "ResourceRecordSet": {
        "Name": "${DOMAIN_1}.",
        "Type": "CNAME",
        "TTL": ${TTL},
        "ResourceRecords": [
          {"Value": "${DOMAIN_1}.${DNS_ROOT_DOMAIN}."}
        ]
      }
    },
    {
      "Action": "CREATE",
      "ResourceRecordSet": {
        "Name": "_acme-challenge.${DOMAIN_1}.",
        "Type": "CNAME",
        "TTL": ${TTL},
        "ResourceRecords": [
          {"Value": "_acme-challenge.${DOMAIN_1}.${DNS_ROOT_DOMAIN}."}
        ]
      }
    }
  ]
}
EOF
  aws route53 change-resource-record-sets \
    --hosted-zone-id "${HOSTED_ZONE_ID}" \
    --change-batch file://./create-cname.json > changeinfo.json
  change_id=$(cat changeinfo.json | jq -r '.ChangeInfo.Id')
  change=$(cat changeinfo.json | jq -r '.ChangeInfo.Status')
  while [[ $change =~ PENDING]]; do 
    sleep 60
    change=$(aws route53 | jq -r '.ChangeInfo.Status')
  done
}

tests() {
  echo "Creating the cf domain objects"
  cf create-domain "$CF_ORGANIZATION" "$DOMAIN_0"
  cf create-domain "$CF_ORGANIZATION" "$DOMAIN_1"
  echo "Sleeping to allow domains to converge"
  sleep 5

  echo "Creating the service instance"
  cf create-service \
    "$SERVICE_NAME" \
    "$PLAN_NAME" \
    "$INSTANCE" \
    -c "{\"domains\": \"$DOMAIN_0, $DOMAIN_1\"}"

  echo "Waiting for the service instance"
  while true; do
    status=$(cf service "$INSTANCE" | grep status:)
    if [[ "$status" =~ succeed ]]; then
      echo "Service instance created."
      break
    elif [[ "$status" =~ progress ]]; then
      sleep 60
    else
      echo "Failed to create service instance:"
      cf service "$INSTANCE"
      exit 1
    fi
  done

  echo "Pushing the test application."
  (
    cd "$(dirname "$0")/app"
    cf push "$INSTANCE" \
      -f manifest.yml \
      --var "domain_0=$DOMAIN_0" \
      --var "domain_1=$DOMAIN_1" \
      --var "name=$INSTANCE"
  )

  echo "Testing the test application through the domains via HTTPS."
  curl -sSL "https://$DOMAIN_0" | grep "ALIVE"
  curl -sSL "https://$DOMAIN_1" | grep "ALIVE"
}

cleanup() {
  set -euxo pipefail
  echo "Deleting the service instance"
  if cf service "$INSTANCE" > /dev/null; then
    cf delete-service -f "$INSTANCE"
  fi

  echo "Deleting the cf domain objects"
  for domain in "$DOMAIN_0" "$DOMAIN_1"; do
    if cf domains | grep -q "$domain"; then
      cf delete-domain -f "$domain"
    fi
  done

  echo "Deleting the application"
  if cf app "$INSTANCE" > /dev/null; then
    cf delete -f "$INSTANCE"
  fi

  # We do this in the end to save some time by deleting the rest of the
  # resources in parllel.
  echo "Waiting for the service instance to finish deleting."
  while true; do
    cf service "$INSTANCE" > /dev/null || break
    sleep 60
  done
  echo "Service instance deleted."
  cat << EOF > ./delete-cname.json
{
  "Changes": [
    {
      "Action": "DELETE",
      "ResourceRecordSet": {
        "Name": "${DOMAIN_0}.",
        "Type": "CNAME",
        "TTL": ${TTL},
        "ResourceRecords": [
          {"Value": "${DOMAIN_0}.${DNS_ROOT_DOMAIN}."}
        ]
      }
    },
    {
      "Action": "DELETE",
      "ResourceRecordSet": {
        "Name": "_acme-challenge.${DOMAIN_0}.",
        "Type": "CNAME",
        "TTL": ${TTL},
        "ResourceRecords": [
          {"Value": "_acme-challenge.${DOMAIN_0}.${DNS_ROOT_DOMAIN}."}
        ]
      }
    },
    {
      "Action": "DELETE",
      "ResourceRecordSet": {
        "Name": "${DOMAIN_1}.",
        "Type": "CNAME",
        "TTL": ${TTL},
        "ResourceRecords": [
          {"Value": "${DOMAIN_1}.${DNS_ROOT_DOMAIN}."}
        ]
      }
    },
    {
      "Action": "DELETE",
      "ResourceRecordSet": {
        "Name": "_acme-challenge.${DOMAIN_1}.",
        "Type": "CNAME",
        "TTL": ${TTL},
        "ResourceRecords": [
          {"Value": "_acme-challenge.${DOMAIN_1}.${DNS_ROOT_DOMAIN}."}
        ]
      }
    }
  ]
}
EOF
  aws route53 change-resource-record-sets \
    --hosted-zone-id "${HOSTED_ZONE_ID}" \
    --change-batch file://./delete-cname.json
}

main
