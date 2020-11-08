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

