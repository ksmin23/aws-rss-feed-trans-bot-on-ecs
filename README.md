# AWS Recent Announcements Rss Feed Translation Bot

영문 [AWS의 최신 소식 (What's New with AWS?)](https://aws.amazon.com/new/)을 한국어로
기계 번역해서 영문과 한국어 번역 내용(아래 그림 참조)을 email로 전송해주는 프로젝트.<br/>

## Architecture


## Deployment


### Docker build

```
docker build -t aws_rss_feed_transbot:latest \
  --build-arg region_name="us-east-1" \
  --build-arg my_s3_bucket_name="s3-bucket-name" \
  --build-arg sender_email="sender@email.com" \
  --build-arg receiver_emails="receiver1@email.com,receiver2@email.com,receiver3@email.com" \
  --build-arg cache_host="localhost" ./
```

tag docker image

```
docker tag aws_rss_feed_transbot:0.1 123456789012.dkr.ecr.us-east-1.amazonaws.com/transbot/rssfeed:0.1
```

push docker image

```
docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/transbot/rssfeed
```

```
$ docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/transbot/rssfeed:0.1
The push refers to repository [123456789012.dkr.ecr.us-east-1.amazonaws.com/transbot/rssfeed]
b576d2933a1e: Preparing 
5438fcfba053: Preparing 
e1dcc4daa2de: Preparing 
8c1ebb1b984d: Preparing 
3196f0b198cb: Preparing 
06b60c6e6ffd: Waiting 
322c3996a80b: Waiting 
225ef82ca30a: Waiting 
d0fe97fa8b8c: Waiting 
denied: Your authorization token has expired. Reauthenticate and try again.
```

To authenticate Docker to an Amazon ECR registry with get-login-password

```
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 123456789012.dkr.ecr.us-east-1.amazonaws.com
```

```
$ aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 123456789012.dkr.ecr.us-east-1.amazonaws.com
WARNING! Your password will be stored unencrypted in /home/ec2-user/.docker/config.json.
Configure a credential helper to remove this warning. See
https://docs.docker.com/engine/reference/commandline/login/#credentials-store

Login Succeeded
```

Retry to push Docker image

```
$ docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/transbot/rssfeed:0.1
The push refers to repository [123456789012.dkr.ecr.us-east-1.amazonaws.com/transbot/rssfeed]
b576d2933a1e: Pushed 
5438fcfba053: Pushed 
e1dcc4daa2de: Pushed 
8c1ebb1b984d: Pushed 
3196f0b198cb: Pushed 
06b60c6e6ffd: Pushed 
322c3996a80b: Pushed 
225ef82ca30a: Pushed 
d0fe97fa8b8c: Pushed 
0.1: digest: sha256:46af6f95bc7fc37319de7d37f6c2148f70494e9f73ff69c0a5baf9d399ba5996 size: 2205
```

Scheduled Tasks

```
cron(0/5 * * * ? *)
```

IAM Policy that is included in `ecsTaskExecutionRole`

S3 Access

```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Action": [
                "s3:AbortMultipartUpload",
                "s3:GetBucketLocation",
                "s3:GetObject",
                "s3:ListBucket",
                "s3:ListBucketMultipartUploads",
                "s3:PutObject"
            ],
            "Resource": [
                "arn:aws:s3:::your-s3-bucket-name/whats-new-html/*"
            ],
            "Effect": "Allow"
        }
    ]
}
```

AmazonSESFullAccess

```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ses:*"
            ],
            "Resource": "*"
        }
    ]
}
```

CDK로 필요한 인프라 만들기 - VPC, ElastiCache for Redis, ECS Cluster, Scheduled Task
Scheduled Task의 Security Group 변경하기 <-- Manual 또는 aws cli를 이용해서
