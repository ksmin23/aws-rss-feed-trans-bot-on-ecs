FROM python:3.8.6-slim
WORKDIR /home/rss-feed-trans-bot
COPY requirements.txt ./
COPY src/main/python/rss_feed_trans_bot.py ./ 
RUN pip install -r requirements.txt

ARG my_s3_bucket_name
ARG sender_email
ARG receiver_emails
ARG cache_host

ENV S3_BUCKET_NAME ${my_s3_bucket_name}
ENV S3_OBJ_KEY_PREFIX "whats-new"
ENV EMAIL_FROM_ADDRESS ${sender_email}
ENV EMAIL_TO_ADDRESSES ${receiver_emails}
ENV ELASTICACHE_HOST ${cache_host}

CMD ["python", "./rss_feed_trans_bot.py"]
