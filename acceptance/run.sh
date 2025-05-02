#!/usr/bin/env bash

# This acceptance test run in CI against a live CF instance, and provisions
# production Let's Encrypt certificates.  The domains (DOMAIN_0 & DOMAIN_1)
# should each be pre-configured in DNS like such:
#
# CNAME $DOMAIN -> $DOMAIN.$DNS_ROOT_DOMAIN
# CNAME _acme-challenge.$DOMAIN -> _acme-challenge.$DOMAIN.$DNS_ROOT_DOMAIN
#
# ($DNS_ROOT_DOMAIN is the value the broker is configured with)

DATESTAMP=$(date +"%Y%m%d%H%M%S")
INSTANCE="edb-test-${PLAN_NAME}-${DATESTAMP}"
TTL=120
# Disable AWS pager to avoid dependency on less.
# see https://stackoverflow.com/a/68361849
export AWS_PAGER=""

required_vars=(
  CF_API_URL
  CF_ORGANIZATION
  CF_PASSWORD
  CF_SPACE
  CF_USERNAME
  DNS_ROOT_DOMAIN
  HOSTED_ZONE_ID_0
  HOSTED_ZONE_ID_1
  TEST_DOMAIN_0
  TEST_DOMAIN_1
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
  DOMAIN_0="${INSTANCE}.${TEST_DOMAIN_0}"
  DOMAIN_1="${INSTANCE}.${TEST_DOMAIN_1}"
  cat << EOF > /tmp/create-cname-0.json
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
    }
  ]
}
EOF
  cat << EOF > /tmp/create-cname-1.json
{
  "Changes": [
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
    --hosted-zone-id "${HOSTED_ZONE_ID_0}" \
    --change-batch file:///tmp/create-cname-0.json > /tmp/changeinfo0.json
  aws route53 change-resource-record-sets \
    --hosted-zone-id "${HOSTED_ZONE_ID_1}" \
    --change-batch file:///tmp/create-cname-1.json > /tmp/changeinfo1.json
  change_id_0=$(cat /tmp/changeinfo0.json | jq -r '.ChangeInfo.Id')
  change=$(cat /tmp/changeinfo0.json | jq -r '.ChangeInfo.Status')
  while [[ "$change" =~ PENDING ]]; do
    sleep 60
    change=$(aws route53 get-change --id ${change_id_0} | jq -r '.ChangeInfo.Status')
  done
  change_id_1=$(cat /tmp/changeinfo1.json | jq -r '.ChangeInfo.Id')
  change=$(cat /tmp/changeinfo1.json | jq -r '.ChangeInfo.Status')
  while [[ "$change" =~ PENDING ]]; do
    sleep 60
    change=$(aws route53 get-change --id ${change_id_1} | jq -r '.ChangeInfo.Status')
  done
}

tests() {
  echo "Creating the cf domain objects"
  cf create-domain "$CF_ORGANIZATION" "$DOMAIN_0"
  cf create-domain "$CF_ORGANIZATION" "$DOMAIN_1"
  echo "Sleeping to allow domains to converge"
  sleep 5

  if [[ "${PLAN_NAME}" == "domain-with-cdn" ]]; then
    echo "Creating the service instance"
    cf create-service \
      "$SERVICE_NAME" \
      "$PLAN_NAME" \
      "$INSTANCE" \
      -c "{\"domains\": \"$DOMAIN_0, $DOMAIN_1\", \"forward_cookies\": \"cookieone, cookietwo\", \"forward_headers\": \"x-one-header,x-two-header\", \"error_responses\": {\"404\": \"/errors/404.html\"}}"
  elif [[ "${PLAN_NAME}" == "domain-with-cdn-dedicated-waf" ]]; then
    echo "Creating the service instance"
    cf create-service \
      "$SERVICE_NAME" \
      "$PLAN_NAME" \
      "$INSTANCE" \
      -c "{\"domains\": \"$DOMAIN_0, $DOMAIN_1\", \"alarm_notification_email\": \"$ALARM_NOTIFICATION_EMAIL\", \"cache_policy\": \"Managed-CachingOptimized\", \"origin_request_policy\": \"Managed-AllViewer\", \"error_responses\": {\"404\": \"/errors/404.html\"}}"
  else
    echo "Creating the service instance"
    cf create-service \
      "$SERVICE_NAME" \
      "$PLAN_NAME" \
      "$INSTANCE" \
      -c "{\"domains\": \"$DOMAIN_0, $DOMAIN_1\"}"
  fi

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
    cf delete-service -f "$INSTANCE" &
  fi

  echo "Deleting the cf domain objects"
  for domain in "$DOMAIN_0" "$DOMAIN_1"; do
    if cf domains | grep -q "$domain"; then
      cf delete-domain -f "$domain" &
    fi
  done

  echo "Deleting the application"
  if cf app "$INSTANCE" > /dev/null; then
    cf delete -f "$INSTANCE" &
  fi

  cat << EOF > /tmp/delete-cname-0.json
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
    }
  ]
}
EOF
cat << EOF > /tmp/delete-cname-1.json
{
  "Changes": [
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
    --hosted-zone-id "${HOSTED_ZONE_ID_0}" \
    --change-batch file:///tmp/delete-cname-0.json &
  aws route53 change-resource-record-sets \
    --hosted-zone-id "${HOSTED_ZONE_ID_1}" \
    --change-batch file:///tmp/delete-cname-1.json &

  echo "Waiting for the service instance to finish deleting."
  while true; do
    cf service "$INSTANCE" > /dev/null || break
    sleep 60
  done
  echo "Service instance deleted."
}

main
