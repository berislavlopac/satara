#!/bin/sh
# Creates the bucket, the upload queue and its dead-letter queue, and has the bucket notify
# the queue of every upload. Safe to run again. On AWS the queue would also need a policy
# that lets the bucket send to it.
set -eu

until aws s3api list-buckets >/dev/null 2>&1; do sleep 1; done

aws s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1 \
    || aws s3api create-bucket --bucket "$BUCKET" >/dev/null

# Kept for 14 days, the most SQS allows.
dead_letter_url=$(aws sqs create-queue --queue-name "$QUEUE-dead-letter" \
    --attributes MessageRetentionPeriod=1209600 --query QueueUrl --output text)
dead_letter_arn=$(aws sqs get-queue-attributes --queue-url "$dead_letter_url" \
    --attribute-names QueueArn --query Attributes.QueueArn --output text)

# A message stays hidden for 30 minutes once received, long enough for a build, and moves to
# the dead-letter queue after three attempts without being deleted.
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

echo "Storage ready: bucket $BUCKET, queue $QUEUE"
