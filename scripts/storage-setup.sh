#!/bin/sh
# Creates the bucket, the upload queue and its dead-letter queue, and has the bucket notify
# the queue of every upload. Safe to run again. The local stack's emulator runs it when it
# starts; on AWS, run it once, and give the queue a policy that lets the bucket send to it.
set -eu

# Left once every step has succeeded, for the emulator's health check to find.
ready_marker=/tmp/satara-storage-ready
rm -f "$ready_marker"

# The AWS CLI bundled with the emulator ignores AWS_ENDPOINT_URL for SQS, so it is passed to
# every call, when it is set.
aws() {
    command aws ${AWS_ENDPOINT_URL:+--endpoint-url "$AWS_ENDPOINT_URL"} "$@"
}

aws s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1 \
    || aws s3api create-bucket --bucket "$BUCKET" >/dev/null

# A build stopped before it can abort its upload leaves the parts behind; S3 removes them
# after a day.
cat > /tmp/lifecycle.json <<JSON
{
  "Rules": [
    {
      "ID": "remove-unfinished-uploads",
      "Status": "Enabled",
      "Filter": {"Prefix": ""},
      "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1}
    }
  ]
}
JSON
aws s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" \
    --lifecycle-configuration file:///tmp/lifecycle.json >/dev/null

# Kept for 14 days, the most SQS allows.
dead_letter_url=$(aws sqs create-queue --queue-name "$QUEUE-dead-letter" \
    --attributes MessageRetentionPeriod=1209600 --query QueueUrl --output text)
dead_letter_arn=$(aws sqs get-queue-attributes --queue-url "$dead_letter_url" \
    --attribute-names QueueArn --query Attributes.QueueArn --output text)

# A message stays hidden for 30 minutes once received, and moves to the dead-letter queue
# after three attempts without being deleted.
cat > /tmp/queue.json <<JSON
{
  "VisibilityTimeout": "1800",
  "RedrivePolicy": "{\"deadLetterTargetArn\": \"$dead_letter_arn\", \"maxReceiveCount\": \"3\"}"
}
JSON
queue_url=$(aws sqs create-queue --queue-name "$QUEUE" --attributes file:///tmp/queue.json \
    --query QueueUrl --output text)
queue_arn=$(aws sqs get-queue-attributes --queue-url "$queue_url" \
    --attribute-names QueueArn --query Attributes.QueueArn --output text)

cat > /tmp/notification.json <<JSON
{
  "QueueConfigurations": [
    {
      "QueueArn": "$queue_arn",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {"Key": {"FilterRules": [{"Name": "prefix", "Value": "uploads/"}]}}
    }
  ]
}
JSON
aws s3api put-bucket-notification-configuration --bucket "$BUCKET" \
    --notification-configuration file:///tmp/notification.json

touch "$ready_marker"
echo "Storage ready: bucket $BUCKET, queue $QUEUE"
